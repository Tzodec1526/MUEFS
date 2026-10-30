"""Integrity checks on the full Michigan seed data, run against a throwaway SQLite DB.

These guard the curation rules behind the filing checklists:
- one requirement row per (court, case type, document code) — no duplicate cards;
- discovery papers that are served on parties rather than filed with the court
  (MCR 2.302(H)) never appear on a filing checklist;
- the circuit civil checklist stays limited to required / highly probable documents.
"""

import hashlib
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import create_engine, func, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session

import app.seed_data as seed_data
from app.models.case import Case
from app.models.court import CaseType, Court, CourtType, FilingRequirement
from app.models.filing import FilingDocument
from app.models.user import User
from app.readiness import EXPECTED_HEADS
from app.services import access_service, document_service
from app.services.filing_service import requirements_for_filing_type
from tests.test_filing_concurrency import POSTGRES_URL
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

# Served on parties, not filed with the court (MCR 2.302(H)).
SERVED_NOT_FILED_DISCOVERY = {
    "DISC_INTERROG", "DISC_RFP", "DISC_RFA",
    "DISC_ANSWERS", "DISC_RFP_RESP", "DISC_RFA_RESP",
    "DISC_PRIVILEGE", "DISC_EXPERT",
}


@pytest.fixture(scope="module")
def seeded_session(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("seed") / "seed.db"
    url = f"sqlite:///{db_path}"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(document_service, "_local_storage_path", lambda: db_path.parent / "files")
        seed_data.seed_database(url=url)
    engine = create_engine(url)
    with Session(engine) as session:
        session.info["document_root"] = db_path.parent / "files"
        yield session
    engine.dispose()


def test_requirements_unique_per_case_type_and_code(seeded_session):
    dupes = (
        seeded_session.query(
            FilingRequirement.court_id,
            FilingRequirement.case_type_id,
            FilingRequirement.document_type_code,
        )
        .group_by(
            FilingRequirement.court_id,
            FilingRequirement.case_type_id,
            FilingRequirement.document_type_code,
        )
        .having(func.count(FilingRequirement.id) > 1)
        .all()
    )
    assert dupes == []


def test_no_served_only_discovery_papers_on_filing_checklists(seeded_session):
    rows = (
        seeded_session.query(FilingRequirement.document_type_code)
        .filter(FilingRequirement.document_type_code.in_(SERVED_NOT_FILED_DISCOVERY))
        .all()
    )
    assert rows == []


def test_circuit_civil_checklist_is_curated(seeded_session):
    court = seeded_session.query(Court).filter_by(court_type=CourtType.CIRCUIT).first()
    case_type = seeded_session.query(CaseType).filter_by(
        court_id=court.id, code="CIV-GEN"
    ).one()
    reqs = (
        seeded_session.query(FilingRequirement)
        .filter_by(court_id=court.id, case_type_id=case_type.id)
        .all()
    )

    initial = requirements_for_filing_type(reqs, "initial")
    assert {r.document_type_code for r in initial if r.is_required} == {
        "COMPLAINT", "SUMMONS",
    }
    assert {r.document_type_code for r in initial if not r.is_required} == {
        "EXHIBIT", "JURY_DEMAND",
    }

    motion = requirements_for_filing_type(reqs, "motion")
    # DISC_CERT_GF is recommended, not required: MCR 2.313(A)(5) makes a good-faith effort
    # a factor in awarding motion expenses, not a required filing.
    assert {r.document_type_code for r in motion if r.is_required} == {
        "MOTION",
    }
    assert {r.document_type_code for r in motion if not r.is_required} == {
        "BRIEF_SUPPORT", "PROPOSED_ORDER", "NOT_HEARING", "DISC_CERT_GF",
    }


def test_circuit_court_names_use_correct_ordinals(seeded_session):
    names = {
        name
        for (name,) in seeded_session.query(Court.name).filter(
            Court.court_type == CourtType.CIRCUIT
        )
    }
    assert len(names) == 57
    # One row per circuit number, so presence of the correct ordinal implies
    # the naive "21th"-style name is gone.
    for good in (
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th",
        "21st", "22nd", "23rd", "31st", "32nd", "33rd",
        "41st", "42nd", "43rd", "51st", "52nd", "53rd",
    ):
        assert f"{good} Circuit Court" in names, good


def test_seed_reset_flag_rebuilds_from_scratch(tmp_path, monkeypatch):
    """--reset drops and reseeds the app tables; a plain rerun still skips."""
    url = f"sqlite:///{tmp_path / 'reset.db'}"
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path / "files")
    engine = create_engine(url)
    try:
        seed_data.seed_database(url=url)
        with Session(engine) as session:
            baseline_courts = session.query(Court).count()
            session.query(FilingRequirement).delete()
            session.commit()

        # Without reset, seeding sees existing courts and skips — damage stays.
        seed_data.seed_database(url=url)
        with Session(engine) as session:
            assert session.query(FilingRequirement).count() == 0

        # With reset, the schema is rebuilt and fully reseeded.
        seed_data.seed_database(reset=True, url=url)
        with Session(engine) as session:
            assert session.query(Court).count() == baseline_courts
            assert session.query(FilingRequirement).count() > 0
    finally:
        engine.dispose()


def test_sample_docket_has_real_marked_documents_with_matching_metadata(seeded_session):
    documents = seeded_session.query(FilingDocument).all()
    assert documents
    for doc in documents:
        payload = (seeded_session.info["document_root"] / doc.file_key).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == doc.sha256_hash
        assert len(payload) == doc.file_size_bytes
        pdf = PdfReader(BytesIO(payload))
        assert len(pdf.pages) == doc.page_count
        assert "DEMONSTRATION ONLY - NOT A COURT FILING" in pdf.pages[0].extract_text()
        assert doc.pii_warnings == []


def test_sample_case_numbers_match_filed_year_and_subject(seeded_session):
    cases = seeded_session.query(Case).order_by(Case.id).all()
    assert len(cases) == 4
    assert [case.case_number for case in cases] == [
        f"{case.filed_date.year:04d}-{index:06d}-{suffix}"
        for index, (case, suffix) in enumerate(zip(cases, ["CZ", "NO", "DM", "PZ"]), 1)
    ]


async def test_sample_participants_can_file_only_on_their_reviewed_cases(seeded_session):
    engine = create_async_engine(f"sqlite+aiosqlite:///{seeded_session.bind.url.database}")
    try:
        async with AsyncSession(engine) as db:
            assert await access_service.user_may_file_on_case(db, await db.get(User, 1), 1)
            assert await access_service.user_may_file_on_case(db, await db.get(User, 1), 2)
            assert await access_service.user_may_file_on_case(db, await db.get(User, 4), 2)
            assert not await access_service.user_may_file_on_case(db, await db.get(User, 4), 1)
            assert not await access_service.user_may_file_on_case(db, await db.get(User, 1), 3)
            assert not await access_service.user_may_file_on_case(db, await db.get(User, 5), 1)
    finally:
        await engine.dispose()


def test_async_driver_seed_matches_sync_seed(seeded_session, tmp_path, monkeypatch):
    """PostgreSQL seeds through asyncpg; aiosqlite exercises the same driver bridge."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'async-seed.db'}"
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path / "files")
    engine = create_engine(f"sqlite:///{tmp_path / 'async-seed.db'}")
    models = (Court, CaseType, FilingRequirement, FilingDocument)
    expected = [seeded_session.query(model).count() for model in models]

    def seeded_counts():
        with Session(engine) as session:
            assert {session.scalar(text("SELECT version_num FROM alembic_version"))} == (
                EXPECTED_HEADS
            )
            return [session.query(model).count() for model in models]

    try:
        seed_data.seed_database(url=url)
        assert seeded_counts() == expected
        with Session(engine) as session:
            session.query(FilingRequirement).delete()
            session.commit()
        seed_data.seed_database(url=url)  # A rerun keeps existing data.
        assert seeded_counts()[2] == 0
        seed_data.seed_database(reset=True, url=url)
        assert seeded_counts() == expected
    finally:
        engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")
@pytest.mark.parametrize("postgres_sessions", ["c39f64dbea05"], indirect=True)
async def test_reset_rebuilds_a_postgresql_schema_from_an_earlier_release(postgres_sessions):
    # Earlier releases left the notices' old enum type behind; the reset must not fail on it.
    engine = postgres_sessions.kw["bind"]
    async with engine.connect() as connection:
        await connection.run_sync(seed_data._prepare_schema, True)
    async with engine.connect() as connection:
        leftover = await connection.scalar(text(
            "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE t.typname = 'deliverystatus' AND n.nspname = current_schema()"
        ))
        versions = set(await connection.scalars(text("SELECT version_num FROM alembic_version")))
    assert leftover == 0
    assert versions == set(EXPECTED_HEADS)
