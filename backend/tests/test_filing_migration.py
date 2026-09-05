"""Retained-history upgrades must preserve old filing data and migrate without reset."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from alembic import command
from app.demo.schema import prepare_demo_schema
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import User, UserType


def test_unversioned_demo_upgrade_preserves_filings(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    try:
        prepare_demo_schema(engine)
        with Session(engine) as db:
            user = User(
                email="legacy@test.com",
                first_name="Legacy",
                last_name="Filer",
                user_type=UserType.ATTORNEY,
            )
            court = Court(name="Legacy Court", county="Wayne", court_type=CourtType.CIRCUIT)
            db.add_all([user, court])
            db.flush()
            case_type = CaseType(
                court_id=court.id, code="CIV", name="Civil", category=CaseCategory.CIVIL
            )
            db.add(case_type)
            db.flush()
            filing = FilingEnvelope(
                court_id=court.id,
                case_type_id=case_type.id,
                filer_id=user.id,
                status=FilingStatus.RETURNED,
                submitted_at=datetime.now(UTC),
                fee_waiver_requested=True,
                fee_waiver_granted=True,
            )
            db.add(filing)
            db.flush()
            db.add(
                FilingDocument(
                    envelope_id=filing.id,
                    title="Original",
                    document_type_code="FEE_WAIVER",
                    file_key="keep-me",
                    file_size_bytes=10,
                    mime_type="text/plain",
                    sha256_hash="a" * 64,
                )
            )
            db.commit()
        # Reproduce the prior create_all schema, which had no version table or receipts.
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE filing_transactions"))
            conn.execute(text("DROP TABLE alembic_version"))
            conn.execute(text("DROP TABLE court_calendars"))
            conn.execute(text("ALTER TABLE filing_envelopes DROP COLUMN filing_date"))
            conn.execute(text("ALTER TABLE filing_envelopes DROP COLUMN filing_date_basis"))
            conn.execute(text("ALTER TABLE cases DROP COLUMN filing_date"))
            conn.execute(text("DROP INDEX ix_filing_court_waiver"))
            conn.execute(text("ALTER TABLE filing_envelopes DROP COLUMN fee_waiver_referred_at"))
            conn.execute(text("ALTER TABLE filing_envelopes DROP COLUMN fee_waiver_decided_at"))
            conn.execute(text(
                "ALTER TABLE filing_envelopes DROP COLUMN fee_waiver_amount_due_cents"
            ))
            conn.execute(text("ALTER TABLE filing_envelopes DROP COLUMN submission_count"))
            conn.execute(text("ALTER TABLE filing_documents DROP COLUMN retained_at"))
            conn.execute(text("ALTER TABLE filing_documents DROP COLUMN removed_at"))
        prepare_demo_schema(engine)
        prepare_demo_schema(engine)  # Booting again must not reapply or duplicate anything.
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT file_key FROM filing_documents")) == "keep-me"
            assert conn.scalar(text("SELECT retained_at FROM filing_documents")) is not None
            assert conn.scalar(text("SELECT is_confidential FROM filing_documents")) == 1
            assert conn.scalar(text("SELECT count(*) FROM filing_transactions")) == 0
            assert conn.scalar(text("SELECT status FROM filing_envelopes")) == "RETURNED"
            assert conn.scalar(text("SELECT fee_waiver_granted FROM filing_envelopes")) == 1
            assert conn.scalar(text("SELECT fee_waiver_decided_at FROM filing_envelopes")) is None
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "a8b712e43c90"
            assert conn.scalar(text("SELECT filing_date FROM filing_envelopes")) is None
    finally:
        engine.dispose()


def test_versioned_migration_installs_retention_guards(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migrated.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    try:
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "c4f8e2a91b0d")
            command.upgrade(config, "head")
            assert "filing_transactions" in inspect(conn).get_table_names()
            guards = conn.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger'")).all()
            assert set(guards) == {"filing_transactions_no_update", "filing_transactions_no_delete",
                                   "court_calendars_no_update", "court_calendars_no_delete"}
            with pytest.raises(RuntimeError, match="cannot be downgraded"):
                command.downgrade(config, "c4f8e2a91b0d")
    finally:
        engine.dispose()
