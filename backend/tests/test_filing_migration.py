"""Upgrade real historical schemas without coupling the fixture to today's models."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table, create_engine, text

from alembic import command
from app.demo.schema import prepare_demo_schema


def test_unversioned_demo_upgrade_preserves_filings(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    try:
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "c4f8e2a91b0d")
            # Use the actual old tables, not the current ORM followed by destructive surgery.
            metadata = MetaData()
            rows = [
                (
                    "users",
                    dict(
                        id=1,
                        email="legacy@test.com",
                        first_name="Legacy",
                        last_name="Filer",
                        user_type="ATTORNEY",
                        bar_number_verified=False,
                        is_active=True,
                    ),
                ),
                (
                    "courts",
                    dict(
                        id=1,
                        name="Legacy Court",
                        county="Wayne",
                        court_type="CIRCUIT",
                        state="MI",
                        is_efiling_enabled=True,
                    ),
                ),
                (
                    "case_types",
                    dict(
                        id=1,
                        court_id=1,
                        code="CIV",
                        name="Civil",
                        category="CIVIL",
                        filing_fee_cents=0,
                        is_active=True,
                    ),
                ),
                (
                    "cases",
                    dict(
                        id=1,
                        court_id=1,
                        case_type_id=1,
                        case_number="LEGACY-1",
                        title="Preserved case",
                        status="OPEN",
                        is_sealed=True,
                        filed_date=datetime.now(UTC),
                    ),
                ),
                (
                    "case_participants",
                    dict(
                        id=1,
                        case_id=1,
                        user_id=1,
                        role="ATTORNEY_PLAINTIFF",
                        party_name="Legacy counsel",
                        attorney_bar_number="P12345",
                        contact_email="private@example.com",
                        contact_phone="555-0100",
                        contact_address="Original contact address",
                    ),
                ),
                (
                    "filing_envelopes",
                    dict(
                        id=1,
                        court_id=1,
                        case_type_id=1,
                        filer_id=1,
                        filing_type="initial",
                        status="RETURNED",
                        submitted_at=datetime.now(UTC),
                        fee_waiver_requested=True,
                        fee_waiver_granted=True,
                    ),
                ),
                (
                    "filing_documents",
                    dict(
                        id=1,
                        envelope_id=1,
                        title="Original",
                        document_type_code="FEE_WAIVER",
                        file_key="keep-me",
                        file_size_bytes=10,
                        mime_type="text/plain",
                        sha256_hash="a" * 64,
                        is_confidential=False,
                        is_text_searchable=False,
                    ),
                ),
                (
                    "notifications",
                    dict(
                        id=1,
                        notification_type="CASE_UPDATE",
                        recipient_id=1,
                        filing_envelope_id=1,
                        subject="Legacy update",
                        body="Preserve this notice",
                        delivery_status="PENDING",
                    ),
                ),
            ]
            for name, values in rows:
                conn.execute(Table(name, metadata, autoload_with=conn).insert().values(**values))
            conn.execute(
                metadata.tables["notifications"]
                .insert()
                .values(
                    id=2,
                    notification_type="CASE_UPDATE",
                    recipient_id=1,
                    subject="Old sent status",
                    body="Original historical notice",
                    delivery_status="SENT",
                )
            )
            grants = Table("user_court_roles", metadata, autoload_with=conn)
            conn.execute(
                grants.insert(),
                [
                    {"id": 1, "user_id": 1, "court_id": 1, "role": "CLERK"},
                    {"id": 2, "user_id": 1, "court_id": 1, "role": "CLERK"},
                ],
            )
            conn.execute(text("DROP TABLE alembic_version"))
        prepare_demo_schema(engine)
        prepare_demo_schema(engine)  # A second boot must not reapply or duplicate anything.
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT file_key FROM filing_documents")) == "keep-me"
            assert conn.scalar(text("SELECT retained_at FROM filing_documents")) is not None
            assert conn.scalar(text("SELECT is_confidential FROM filing_documents")) == 1
            assert conn.scalar(text("SELECT count(*) FROM filing_transactions")) == 0
            assert conn.scalar(text("SELECT status FROM filing_envelopes")) == "RETURNED"
            assert conn.scalar(text("SELECT fee_waiver_granted FROM filing_envelopes")) == 1
            assert conn.scalar(text("SELECT fee_waiver_decided_at FROM filing_envelopes")) is None
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == (
                ScriptDirectory.from_config(config).get_current_head()
            )
            assert conn.scalar(text("SELECT filing_date FROM filing_envelopes")) is None
            assert conn.scalar(text("SELECT verified_email FROM users")) is None
            assert conn.scalar(text("SELECT administration_version FROM users")) == 0
            assert conn.scalar(text("SELECT count(*) FROM user_court_roles")) == 1
            duplicate = conn.execute(
                text(
                    "SELECT action, details FROM audit_log "
                    "WHERE action='identity.duplicate_role_removed'"
                )
            ).one()
            assert duplicate.action == "identity.duplicate_role_removed"
            assert '"former_id": 2' in duplicate.details
            participant = conn.execute(text("SELECT * FROM case_participants")).mappings().one()
            assert participant["user_id"] == 1 and participant["role"] == "ATTORNEY_PLAINTIFF"
            assert participant["party_name"] == "Legacy counsel"
            assert participant["attorney_bar_number"] == "P12345"
            assert participant["contact_email"] == "private@example.com"
            assert participant["contact_phone"] == "555-0100"
            assert participant["contact_address"] == "Original contact address"
            assert participant["is_active"] == 1 and participant["access_enabled"] == 0
            assert participant["reviewed_at"] is None
            assert conn.scalar(text("SELECT participant_version FROM cases")) == 0
            assert (
                conn.scalar(
                    text(
                        "SELECT count(*) FROM audit_log "
                        "WHERE action='case.participants_review_required'"
                    )
                )
                == 1
            )
            assert (
                conn.scalar(text("SELECT delivery_status FROM notifications WHERE id=1"))
                == "DISABLED"
            )
            assert (
                conn.scalar(text("SELECT delivery_status FROM notifications WHERE id=2"))
                == "LEGACY"
            )
            assert (
                conn.scalar(text("SELECT detail FROM notification_delivery_events"))
                == "Pre-outbox status: SENT"
            )
            assert (
                conn.scalar(text("SELECT body FROM notifications WHERE id=1"))
                == "Preserve this notice"
            )
            assert conn.scalar(text("SELECT email_message FROM notifications")) is None
    finally:
        engine.dispose()


def test_retained_history_cannot_be_downgraded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migrated.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    try:
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "c4f8e2a91b0d")
            command.upgrade(config, "head")
            with pytest.raises(RuntimeError, match="cannot be downgraded"):
                command.downgrade(config, "c4f8e2a91b0d")
    finally:
        engine.dispose()
