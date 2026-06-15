"""Integrity checks on the full Michigan seed data, run against a throwaway SQLite DB.

These guard the curation rules behind the filing checklists:
- one requirement row per (court, case type, document code) — no duplicate cards;
- discovery papers that are served on parties rather than filed with the court
  (MCR 2.302(H)) never appear on a filing checklist;
- the circuit civil checklist stays limited to required / highly probable documents.
"""

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

import app.seed_data as seed_data
from app.models.court import CaseType, Court, CourtType, FilingRequirement
from app.services.filing_service import requirements_for_filing_type

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
    original = seed_data.DATABASE_URL
    seed_data.DATABASE_URL = url
    try:
        seed_data.seed_database()
    finally:
        seed_data.DATABASE_URL = original
    engine = create_engine(url)
    with Session(engine) as session:
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


def test_seed_reset_flag_rebuilds_from_scratch(tmp_path):
    """--reset drops and reseeds the app tables; a plain rerun still skips."""
    url = f"sqlite:///{tmp_path / 'reset.db'}"
    original = seed_data.DATABASE_URL
    seed_data.DATABASE_URL = url
    engine = create_engine(url)
    try:
        seed_data.seed_database()
        with Session(engine) as session:
            baseline_courts = session.query(Court).count()
            session.query(FilingRequirement).delete()
            session.commit()

        # Without reset, seeding sees existing courts and skips — damage stays.
        seed_data.seed_database()
        with Session(engine) as session:
            assert session.query(FilingRequirement).count() == 0

        # With reset, the schema is rebuilt and fully reseeded.
        seed_data.seed_database(reset=True)
        with Session(engine) as session:
            assert session.query(Court).count() == baseline_courts
            assert session.query(FilingRequirement).count() > 0
    finally:
        engine.dispose()
        seed_data.DATABASE_URL = original
