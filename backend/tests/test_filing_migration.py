"""Upgrade real historical schemas without coupling the fixture to today's models."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.demo.schema import prepare_demo_schema
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions


@pytest.mark.skipif(not os.getenv("MUEFS_TEST_POSTGRES_URL"), reason="PostgreSQL not configured")
@pytest.mark.parametrize("postgres_sessions", ["d4e7a12b93f0"], indirect=True)
async def test_search_index_upgrade_recovers_failed_build_and_preserves_records(postgres_sessions):
    from app.models.case import Case, CaseParticipant, ParticipantRole
    from app.models.court import CaseCategory, CaseType, Court, CourtType
    from app.services.search_service import search_cases

    engine = postgres_sessions.kw["bind"]
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    async with engine.connect() as conn:
        def downgrade(connection):
            config.attributes["connection"] = connection
            command.downgrade(config, "c3d9f06a21b8")
        await conn.run_sync(downgrade)

    async with postgres_sessions.begin() as db:
        court = Court(name="Search Court", county="Wayne", court_type=CourtType.CIRCUIT)
        db.add(court)
        await db.flush()
        case_type = CaseType(court_id=court.id, code="CIV", name="Civil",
                             category=CaseCategory.CIVIL, filing_fee_cents=0)
        db.add(case_type)
        await db.flush()
        case = Case(court_id=court.id, case_type_id=case_type.id, case_number="2026-100%_A",
                    title="Retained public matter", filed_date=datetime.now(UTC))
        db.add(case)
        await db.flush()
        db.add(CaseParticipant(case_id=case.id, party_name="Jane Public",
                               role=ParticipantRole.PLAINTIFF))

    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        # Emulate a partial migration: one completed build and one real failed build.
        await conn.execute(text("""CREATE INDEX CONCURRENTLY ix_cases_case_number_trgm
            ON cases USING gin (case_number public.gin_trgm_ops)"""))
        with pytest.raises(DBAPIError, match="invalid input syntax for type integer"):
            await conn.execute(text("""
                CREATE INDEX CONCURRENTLY ix_case_participants_party_name_trgm
                ON case_participants ((party_name::integer))"""))
        assert await conn.scalar(text("""SELECT indisvalid FROM pg_index
            WHERE indexrelid = 'ix_case_participants_party_name_trgm'::regclass""")) is False

    for target, kind in [("d4e7a12b93f0", "gin"), ("c3d9f06a21b8", "btree"),
                         ("d4e7a12b93f0", "gin")]:
        async with engine.connect() as conn:
            def migrate(connection):
                config.attributes["connection"] = connection
                (command.upgrade if kind == "gin" else command.downgrade)(config, target)
            await conn.run_sync(migrate)
            indexes = (await conn.execute(text("""
                SELECT c.relname, i.indisvalid, a.amname FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_am a ON a.oid = c.relam
                WHERE n.nspname = current_schema() AND c.relname IN (
                    'ix_cases_case_number', 'ix_cases_case_number_trgm',
                    'ix_case_participants_party_name', 'ix_case_participants_party_name_trgm')
                ORDER BY c.relname
            """))).all()
            suffix = "_trgm" if kind == "gin" else ""
            assert indexes == [
                (f"ix_case_participants_party_name{suffix}", True, kind),
                (f"ix_cases_case_number{suffix}", True, kind),
            ]
            assert await conn.scalar(text(
                "SELECT count(*) FROM pg_extension WHERE extname='pg_trgm'"
            )) == 1
        async with postgres_sessions() as db:
            found, total = await search_cases(db, case_number="%_", party_name="jane")
            assert total == 1
            assert [record.id for record in found] == [case.id]


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
                    "service_contacts",
                    dict(case_id=1, user_id=1, name="Legacy service contact",
                         email="legacy-service@example.com", method="ELECTRONIC"),
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
            assert conn.scalar(text("SELECT pii_warnings FROM filing_documents")) is None
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
            service = conn.execute(text("SELECT * FROM service_contacts")).mappings().one()
            assert service["name"] == "Legacy service contact"
            assert service["email"] == "legacy-service@example.com"
            assert service["participant_id"] is None and service["participant_snapshot"] is None
            assert service["reviewed_at"] is None and service["authority"] is None
            assert service["is_active"] == 0 and service["version"] == 0
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


def test_fee_migration_preserves_only_unambiguous_payment_links(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-payments.db'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    try:
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "b2e4a8c19d70")
            conn.execute(text("""INSERT INTO users
                (id, email, first_name, last_name, user_type, bar_number_verified, is_active)
                VALUES (1, 'filer@test.com', 'Fee', 'Filer', 'ATTORNEY', false, true),
                       (2, 'other@test.com', 'Other', 'Filer', 'ATTORNEY', false, true)"""))
            conn.execute(text("""INSERT INTO courts
                (id, name, county, court_type, state, is_efiling_enabled)
                VALUES (1, 'Fee Court', 'Wayne', 'CIRCUIT', 'MI', true)"""))
            conn.execute(text("""INSERT INTO case_types
                (id, court_id, code, name, category, filing_fee_cents, is_active)
                VALUES (1, 1, 'CIV', 'Civil', 'CIVIL', 0, true)"""))
            conn.execute(text("""INSERT INTO payments (id, amount_cents, status, payer_id)
                VALUES (1, 1000, 'COMPLETED', 1), (2, 1000, 'COMPLETED', 1),
                       (3, 1000, 'COMPLETED', 2), (4, 1000, 'COMPLETED', 1)"""))
            conn.execute(text("""INSERT INTO filing_envelopes
                (id, court_id, case_type_id, filer_id, payment_id, status,
                 filing_type, fee_waiver_requested)
                VALUES (1, 1, 1, 1, 1, 'DRAFT', 'initial', false),
                       (2, 1, 1, 1, 2, 'DRAFT', 'initial', false),
                       (3, 1, 1, 1, 2, 'DRAFT', 'initial', false),
                       (4, 1, 1, 1, 3, 'DRAFT', 'initial', false)"""))
            command.upgrade(config, "head")
            assert conn.execute(text(
                "SELECT id, envelope_id, is_simulated, fee_basis FROM payments ORDER BY id"
            )).all() == [
                (1, 1, 1, None), (2, None, 1, None), (3, None, 1, None), (4, None, 1, None),
            ]
            assert conn.scalar(text("SELECT COUNT(*) FROM filing_transactions")) == 0
            assert conn.scalar(text(
                "SELECT COUNT(*) FROM filing_envelopes WHERE fee_version = 0"
            )) == 4
            assert conn.scalar(text("""SELECT COUNT(*) FROM sqlite_master
                WHERE type='index' AND name='ix_users_email_lower'""")) == 1
    finally:
        engine.dispose()


def seed_historical_filings(connection, count):
    metadata = MetaData()
    for name, rows in [
        ("users", [dict(id=i, email=f"legacy{i}@test.com", first_name="Legacy", last_name="Filer",
                        user_type="ATTORNEY", bar_number_verified=False, is_active=True)
                   for i in (1, 2)]),
        ("courts", [dict(id=1, name="Legacy Court", county="Wayne", court_type="CIRCUIT",
                         state="MI", is_efiling_enabled=True)]),
        ("case_types", [dict(id=1, court_id=1, code="CIV", name="Civil", category="CIVIL",
                             filing_fee_cents=0, is_active=True)]),
        ("filing_envelopes", [dict(
            id=number + 1, court_id=1, case_type_id=1, filer_id=2 if number % 5 == 0 else 1,
            case_title=f"Matter {number}", filing_type="initial", fee_waiver_requested=False,
            status="RETURNED" if number % 3 else "DRAFT",
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        ) for number in range(count)]),
    ]:
        table = Table(name, metadata, autoload_with=connection)
        connection.execute(table.insert(), rows)


@pytest.mark.skipif(not os.getenv("MUEFS_TEST_POSTGRES_URL"), reason="PostgreSQL not configured")
@pytest.mark.parametrize("postgres_sessions", ["f7a21b84d903"], indirect=True)
async def test_filer_index_recovers_failed_build_without_changing_pages(postgres_sessions):
    from app.models.filing import FilingStatus
    from app.services.filing_service import list_filings

    engine = postgres_sessions.kw["bind"]
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    async with engine.begin() as conn:
        await conn.run_sync(seed_historical_filings, 41)
    filer = 1
    async with postgres_sessions() as db:
        before = [await list_filings(db, filer, status=status, page=2, page_size=5)
                  for status in [None, FilingStatus.RETURNED]]

    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        # Failed expression conversion leaves a real invalid concurrent index.
        with pytest.raises(DBAPIError, match="invalid input syntax for type integer"):
            await conn.execute(text("""CREATE INDEX CONCURRENTLY ix_filing_filer_updated
                ON filing_envelopes ((case_title::integer))"""))
        assert await conn.scalar(text("""SELECT indisvalid FROM pg_index
            WHERE indexrelid = 'ix_filing_filer_updated'::regclass""")) is False

    for upgrade in [True, False, True]:
        async with engine.connect() as conn:
            def migrate(connection):
                config.attributes["connection"] = connection
                if upgrade:
                    command.upgrade(config, "9d34e6a81c72")
                else:
                    command.downgrade(config, "f7a21b84d903")
            await conn.run_sync(migrate)
            indexes = (await conn.execute(text("""
                SELECT c.relname, i.indisvalid FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname IN (
                    'ix_filing_filer_updated', 'ix_filing_envelopes_filer_id')
            """))).all()
            expected = "ix_filing_filer_updated" if upgrade else "ix_filing_envelopes_filer_id"
            assert indexes == [(expected, True)]
        async with postgres_sessions() as db:
            after = [await list_filings(db, filer, status=status, page=2, page_size=5)
                     for status in [None, FilingStatus.RETURNED]]
            assert after == before


@pytest.mark.skipif(not os.getenv("MUEFS_TEST_POSTGRES_URL"), reason="PostgreSQL not configured")
@pytest.mark.parametrize("postgres_sessions", ["9d34e6a81c72"], indirect=True)
async def test_creation_key_migration_recovers_partial_build_and_retains_keys(postgres_sessions):
    engine = postgres_sessions.kw["bind"]
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    async with engine.begin() as conn:
        await conn.run_sync(seed_historical_filings, 3)
        before = (await conn.execute(text(
            "SELECT id, case_title, status FROM filing_envelopes ORDER BY id"
        ))).all()
        await conn.execute(text("ALTER TABLE filing_envelopes ADD COLUMN creation_key varchar(36)"))
        await conn.execute(text(
            "ALTER TABLE filing_envelopes ADD COLUMN creation_sha256 varchar(64)"
        ))
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        with pytest.raises(DBAPIError, match="invalid input syntax for type integer"):
            await conn.execute(text("""CREATE UNIQUE INDEX CONCURRENTLY uq_filing_creation_key
                ON filing_envelopes ((case_title::integer))"""))
        assert await conn.scalar(text("""SELECT indisvalid FROM pg_index
            WHERE indexrelid = 'uq_filing_creation_key'::regclass""")) is False
    for upgrade in (True, False, True):
        async with engine.connect() as conn:
            def migrate(connection):
                config.attributes["connection"] = connection
                if upgrade:
                    command.upgrade(config, "b63c8e9204af")
                else:
                    command.downgrade(config, "9d34e6a81c72")
            await conn.run_sync(migrate)
            assert (await conn.execute(text(
                "SELECT id, case_title, status FROM filing_envelopes ORDER BY id"
            ))).all() == before
    async with engine.begin() as conn:
        await conn.execute(text("""UPDATE filing_envelopes SET
            creation_key='12345678-1234-1234-1234-123456789012' WHERE id=2"""))
    async with engine.begin() as conn:
        with pytest.raises(DBAPIError, match="uq_filing_creation_key"):
            async with conn.begin_nested():
                await conn.execute(text("""UPDATE filing_envelopes SET
                    creation_key='12345678-1234-1234-1234-123456789012' WHERE id=3"""))
    async with engine.connect() as conn:
        def downgrade_with_keys(connection):
            config.attributes["connection"] = connection
            command.downgrade(config, "9d34e6a81c72")
        with pytest.raises(RuntimeError, match="creation request keys"):
            await conn.run_sync(downgrade_with_keys)


@pytest.mark.skipif(not os.getenv("MUEFS_TEST_POSTGRES_URL"), reason="PostgreSQL not configured")
@pytest.mark.parametrize("postgres_sessions", ["b63c8e9204af"], indirect=True)
async def test_pending_queue_index_recovers_failed_build_and_preserves_results(postgres_sessions):
    from app.services.filing_service import get_clerk_queue

    engine = postgres_sessions.kw["bind"]
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    async with engine.begin() as conn:
        await conn.run_sync(seed_historical_filings, 80)
        await conn.execute(text("""UPDATE filing_envelopes SET status = CASE
            WHEN id % 3 = 0 THEN 'ACCEPTED'::filingstatus
            WHEN id % 3 = 1 THEN 'SUBMITTED'::filingstatus ELSE 'UNDER_REVIEW'::filingstatus END,
            submitted_at = updated_at"""))
        await conn.execute(text("""UPDATE filing_envelopes SET
            creation_key='12345678-1234-1234-1234-123456789012' WHERE id=1"""))
    async with postgres_sessions() as db:
        before = (await get_clerk_queue(db, 1, page=2)).model_dump(exclude={"as_of"})
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        with pytest.raises(DBAPIError, match="invalid input syntax for type integer"):
            await conn.execute(text("""CREATE INDEX CONCURRENTLY ix_filing_pending_received
                ON filing_envelopes ((case_title::integer))"""))
    for upgrade in (True, False, True):
        async with engine.connect() as conn:
            def migrate(connection):
                config.attributes["connection"] = connection
                if upgrade:
                    command.upgrade(config, "c72d9fa083b1")
                else:
                    command.downgrade(config, "b63c8e9204af")
            await conn.run_sync(migrate)
            indexes = (await conn.execute(text("""
                SELECT c.relname, i.indisvalid FROM pg_index i
                JOIN pg_class c ON c.oid=i.indexrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=current_schema() AND c.relname IN
                    ('ix_filing_court_status','ix_filing_pending_received')
            """))).all()
            expected = "ix_filing_pending_received" if upgrade else "ix_filing_court_status"
            assert indexes == [(expected, True)]
            assert await conn.scalar(text(
                "SELECT creation_key FROM filing_envelopes WHERE id=1"
            )) == "12345678-1234-1234-1234-123456789012"
        async with postgres_sessions() as db:
            after = (await get_clerk_queue(db, 1, page=2)).model_dump(exclude={"as_of"})
            assert after == before
