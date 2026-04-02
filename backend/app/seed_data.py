"""Seed data for Michigan Unified E-Filing System.

Populates the database with all Michigan courts, case types,
filing requirements, and demo users.

Usage: python -m app.seed_data
"""

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.court import (
    CaseCategory,
    CaseType,
    CourtType,
    Court,
    FeeSchedule,
    FilingChecklist,
    FilingRequirement,
)
from app.models.user import User, UserType

DATABASE_URL = "postgresql://muefs:muefs_dev@localhost:5432/muefs"

# Michigan Circuit Courts (57 circuits)
CIRCUIT_COURTS = [
    (1, ["Hillsdale"], "Hillsdale"),
    (2, ["Berrien"], "St. Joseph"),
    (3, ["Wayne"], "Detroit"),
    (4, ["Jackson"], "Jackson"),
    (5, ["Barry"], "Hastings"),
    (6, ["Oakland"], "Pontiac"),
    (7, ["Genesee"], "Flint"),
    (8, ["Ionia", "Montcalm"], "Ionia"),
    (9, ["Kalamazoo"], "Kalamazoo"),
    (10, ["Saginaw"], "Saginaw"),
    (11, ["Alger", "Luce", "Schoolcraft"], "Munising"),
    (12, ["Baraga", "Houghton", "Keweenaw"], "Houghton"),
    (13, ["Antrim", "Grand Traverse", "Leelanau"], "Traverse City"),
    (14, ["Muskegon"], "Muskegon"),
    (15, ["Branch"], "Coldwater"),
    (16, ["Macomb"], "Mount Clemens"),
    (17, ["Kent"], "Grand Rapids"),
    (18, ["Bay"], "Bay City"),
    (19, ["Manistee", "Benzie"], "Manistee"),
    (20, ["Ottawa"], "Grand Haven"),
    (21, ["Isabella"], "Mount Pleasant"),
    (22, ["Washtenaw"], "Ann Arbor"),
    (23, ["Alcona", "Arenac", "Iosco", "Oscoda"], "Tawas City"),
    (24, ["Sanilac"], "Sandusky"),
    (25, ["Marquette"], "Marquette"),
    (26, ["Alpena", "Montmorency"], "Alpena"),
    (27, ["Newaygo", "Oceana"], "White Cloud"),
    (28, ["Missaukee", "Wexford"], "Cadillac"),
    (29, ["Clinton", "Gratiot"], "St. Johns"),
    (30, ["Ingham"], "Lansing"),
    (31, ["St. Clair"], "Port Huron"),
    (32, ["Gogebic", "Ontonagon"], "Bessemer"),
    (33, ["Charlevoix"], "Charlevoix"),
    (34, ["Ogemaw", "Roscommon"], "West Branch"),
    (35, ["Shiawassee"], "Corunna"),
    (36, ["Van Buren"], "Paw Paw"),
    (37, ["Calhoun"], "Battle Creek"),
    (38, ["Monroe"], "Monroe"),
    (39, ["Lenawee"], "Adrian"),
    (40, ["Lapeer"], "Lapeer"),
    (41, ["Dickinson", "Iron", "Menominee"], "Iron Mountain"),
    (42, ["Midland"], "Midland"),
    (43, ["Cass"], "Cassopolis"),
    (44, ["Livingston"], "Howell"),
    (45, ["St. Joseph"], "Centreville"),
    (46, ["Crawford", "Kalkaska", "Otsego"], "Gaylord"),
    (47, ["Delta"], "Escanaba"),
    (48, ["Allegan"], "Allegan"),
    (49, ["Mecosta", "Osceola"], "Big Rapids"),
    (50, ["Chippewa"], "Sault Ste. Marie"),
    (51, ["Lake", "Mason"], "Ludington"),
    (52, ["Huron"], "Bad Axe"),
    (53, ["Cheboygan", "Presque Isle"], "Cheboygan"),
    (54, ["Tuscola"], "Caro"),
    (55, ["Clare", "Gladwin"], "Clare"),
    (56, ["Eaton"], "Charlotte"),
    (57, ["Emmet"], "Petoskey"),
]

# Major District Courts
DISTRICT_COURTS = [
    ("36th District Court", "Wayne", "Detroit"),
    ("46th District Court", "Oakland", "Southfield"),
    ("47th District Court", "Oakland", "Farmington Hills"),
    ("48th District Court", "Oakland", "Bloomfield Hills"),
    ("52-1 District Court", "Oakland", "Novi"),
    ("52-2 District Court", "Oakland", "Clarkston"),
    ("52-3 District Court", "Oakland", "Rochester Hills"),
    ("52-4 District Court", "Oakland", "Troy"),
    ("37th District Court", "Macomb", "Warren"),
    ("38th District Court", "Macomb", "Eastpointe"),
    ("39th District Court", "Macomb", "Roseville"),
    ("40th District Court", "Macomb", "St. Clair Shores"),
    ("41A District Court", "Macomb", "Sterling Heights"),
    ("42-1 District Court", "Macomb", "Romeo"),
    ("42-2 District Court", "Macomb", "New Baltimore"),
    ("61st District Court", "Kent", "Grand Rapids"),
    ("62A District Court", "Kent", "Wyoming"),
    ("62B District Court", "Kent", "Kentwood"),
    ("63rd District Court", "Kent", "Grand Rapids"),
    ("67th District Court", "Genesee", "Flint"),
    ("68th District Court", "Genesee", "Flint"),
    ("54A District Court", "Ingham", "Lansing"),
    ("54B District Court", "Ingham", "East Lansing"),
    ("55th District Court", "Ingham", "Mason"),
    ("8th District Court", "Kalamazoo", "Kalamazoo"),
    ("9th District Court", "Kalamazoo", "Kalamazoo"),
    ("14A District Court", "Washtenaw", "Ann Arbor"),
    ("14B District Court", "Washtenaw", "Ypsilanti"),
    ("15th District Court", "Washtenaw", "Ann Arbor"),
    ("1st District Court", "Monroe", "Monroe"),
    ("2A District Court", "Lenawee", "Adrian"),
    ("3A District Court", "Branch", "Coldwater"),
    ("10th District Court", "Calhoun", "Battle Creek"),
    ("5th District Court", "Berrien", "St. Joseph"),
    ("7th District Court", "Van Buren", "Paw Paw"),
    ("73rd District Court", "Saginaw", "Saginaw"),
    ("74th District Court", "Bay", "Bay City"),
    ("70th District Court", "Saginaw", "Saginaw"),
    ("19th District Court", "Macomb", "Dearborn"),
]

# Probate Courts (20 largest counties)
PROBATE_COUNTIES = [
    ("Wayne", "Detroit"),
    ("Oakland", "Pontiac"),
    ("Macomb", "Mount Clemens"),
    ("Kent", "Grand Rapids"),
    ("Genesee", "Flint"),
    ("Washtenaw", "Ann Arbor"),
    ("Ingham", "Lansing"),
    ("Kalamazoo", "Kalamazoo"),
    ("Ottawa", "Grand Haven"),
    ("Saginaw", "Saginaw"),
    ("Muskegon", "Muskegon"),
    ("St. Clair", "Port Huron"),
    ("Livingston", "Howell"),
    ("Monroe", "Monroe"),
    ("Jackson", "Jackson"),
    ("Calhoun", "Battle Creek"),
    ("Bay", "Bay City"),
    ("Berrien", "St. Joseph"),
    ("Allegan", "Allegan"),
    ("Marquette", "Marquette"),
]

# Common case types
CIVIL_CASE_TYPES = [
    ("CIV-GEN", "Civil - General", CaseCategory.CIVIL, 17500),
    ("CIV-TORT", "Civil - Tort", CaseCategory.CIVIL, 17500),
    ("CIV-CONT", "Civil - Contract", CaseCategory.CIVIL, 17500),
    ("CIV-PROP", "Civil - Property", CaseCategory.CIVIL, 17500),
    ("CIV-COND", "Civil - Condemnation", CaseCategory.CIVIL, 17500),
    ("SM-CLM", "Small Claims", CaseCategory.SMALL_CLAIMS, 3000),
]

FAMILY_CASE_TYPES = [
    ("FAM-DIV", "Divorce/Dissolution", CaseCategory.FAMILY, 17500),
    ("FAM-CUST", "Custody", CaseCategory.FAMILY, 17500),
    ("FAM-SUP", "Child Support", CaseCategory.FAMILY, 17500),
    ("FAM-PPO", "Personal Protection Order", CaseCategory.FAMILY, 0),
    ("FAM-ADPT", "Adoption", CaseCategory.FAMILY, 17500),
]

CRIMINAL_CASE_TYPES = [
    ("CR-FEL", "Criminal - Felony", CaseCategory.CRIMINAL, 0),
    ("CR-MISD", "Criminal - Misdemeanor", CaseCategory.CRIMINAL, 0),
    ("TR-CIV", "Traffic - Civil Infraction", CaseCategory.TRAFFIC, 0),
]

PROBATE_CASE_TYPES = [
    ("PR-EST", "Probate - Estate", CaseCategory.PROBATE, 17500),
    ("PR-GRDN", "Probate - Guardianship", CaseCategory.PROBATE, 17500),
    ("PR-CNSRV", "Probate - Conservatorship", CaseCategory.PROBATE, 17500),
    ("PR-TRUST", "Probate - Trust", CaseCategory.PROBATE, 17500),
    ("PR-MI", "Probate - Mentally Ill", CaseCategory.PROBATE, 0),
]

APPEALS_CASE_TYPES = [
    ("APP-CIV", "Appeal - Civil", CaseCategory.APPEALS, 37500),
    ("APP-CR", "Appeal - Criminal", CaseCategory.APPEALS, 37500),
    ("APP-FAM", "Appeal - Family", CaseCategory.APPEALS, 37500),
]

# Filing requirements for civil cases (MCR references)
CIVIL_FILING_REQUIREMENTS = [
    ("COMPLAINT", True, "Complaint", "MCR 2.111", None, None),
    ("SUMMONS", True, "Summons", "MCR 2.102", None, None),
    ("COVER_SHEET", True, "Civil Case Cover Sheet", "MCR 8.119", None, "SCAO Form MC 01"),
    ("PROOF_SERVICE", True, "Proof of Service", "MCR 2.104", None, None),
    ("FILING_FEE", True, "Filing Fee or Fee Waiver", "MCR 2.002", None, None),
    ("EXHIBIT", False, "Exhibits", None, None, "Attach separately; label clearly"),
    ("JURY_DEMAND", False, "Jury Demand", "MCR 2.508", None, None),
]

# Filing requirements for motions
MOTION_FILING_REQUIREMENTS = [
    ("MOTION", True, "Motion", "MCR 2.119", 20, "Brief must not exceed 20 pages"),
    ("BRIEF", True, "Brief in Support", "MCR 2.119(A)(2)", 20, None),
    ("PROPOSED_ORDER", True, "Proposed Order", "MCR 2.119(A)(2)", None, None),
    ("PROOF_SERVICE", True, "Proof of Service", "MCR 2.107", None, None),
    ("NOTICE_HEARING", True, "Notice of Hearing", "MCR 2.119(C)", None, None),
    ("AFFIDAVIT", False, "Supporting Affidavit(s)", None, None, None),
    ("EXHIBIT", False, "Exhibits", None, None, None),
]


def seed_database():
    engine = create_engine(DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Check if already seeded
        existing = session.query(Court).first()
        if existing:
            print("Database already seeded. Skipping.")
            return

        print("Seeding Michigan courts...")

        # --- Demo Users ---
        users = [
            User(
                email="attorney@demo.muefs.gov",
                first_name="Jane",
                last_name="Doe",
                user_type=UserType.ATTORNEY,
                bar_number="P12345",
                firm_name="Doe & Associates PLLC",
                phone="313-555-0100",
            ),
            User(
                email="clerk@demo.muefs.gov",
                first_name="Robert",
                last_name="Johnson",
                user_type=UserType.CLERK,
                phone="313-555-0200",
            ),
            User(
                email="admin@demo.muefs.gov",
                first_name="Admin",
                last_name="User",
                user_type=UserType.ADMIN,
                phone="517-555-0300",
            ),
        ]
        session.add_all(users)
        session.flush()
        print(f"  Created {len(users)} demo users")

        court_count = 0

        # --- Circuit Courts ---
        for circuit_num, counties, city in CIRCUIT_COURTS:
            county = counties[0]
            name = f"{circuit_num}{'st' if circuit_num == 1 else 'nd' if circuit_num == 2 else 'rd' if circuit_num == 3 else 'th'} Circuit Court"
            if len(counties) > 1:
                division = ", ".join(counties) + " Counties"
            else:
                division = f"{county} County"

            court = Court(
                name=name,
                county=county,
                court_type=CourtType.CIRCUIT,
                division=division,
                city=city,
                state="MI",
                cms_type="JIS",
                is_efiling_enabled=True,
            )
            session.add(court)
            session.flush()

            # Add case types
            for code, type_name, category, fee in CIVIL_CASE_TYPES + FAMILY_CASE_TYPES + CRIMINAL_CASE_TYPES:
                ct = CaseType(
                    court_id=court.id,
                    code=code,
                    name=type_name,
                    category=category,
                    filing_fee_cents=fee,
                )
                session.add(ct)

            session.flush()

            # Add filing requirements for civil cases
            civil_ct = session.query(CaseType).filter_by(
                court_id=court.id, code="CIV-GEN"
            ).first()
            if civil_ct:
                for doc_code, required, desc, mcr, page_limit, notes in CIVIL_FILING_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=civil_ct.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))

                # Add checklist for summary disposition
                session.add(FilingChecklist(
                    court_id=court.id,
                    case_type_id=civil_ct.id,
                    motion_type="Summary Disposition (MCR 2.116)",
                    checklist_items={
                        "items": [
                            {"label": "Motion for Summary Disposition", "required": True},
                            {"label": "Brief in Support of Motion", "required": True},
                            {"label": "Statement of Material Facts", "required": True},
                            {"label": "Proposed Order", "required": True},
                            {"label": "Proof of Service", "required": True},
                            {"label": "Supporting Affidavits", "required": False},
                            {"label": "Exhibits", "required": False},
                        ]
                    },
                    help_text="Filed under MCR 2.116. Brief limited to 20 pages. Response due 21 days after service.",
                    mcr_url="https://courts.michigan.gov/courts/michigansupremecourt/rules/court-rules-702/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2116-summary-disposition",
                ))

            court_count += 1

        print(f"  Created {court_count} circuit courts")

        # --- District Courts ---
        dc_count = 0
        for name, county, city in DISTRICT_COURTS:
            court = Court(
                name=name,
                county=county,
                court_type=CourtType.DISTRICT,
                city=city,
                state="MI",
                cms_type="JIS",
                is_efiling_enabled=True,
            )
            session.add(court)
            session.flush()

            for code, type_name, category, fee in CIVIL_CASE_TYPES + CRIMINAL_CASE_TYPES:
                session.add(CaseType(
                    court_id=court.id,
                    code=code,
                    name=type_name,
                    category=category,
                    filing_fee_cents=fee,
                ))

            dc_count += 1

        print(f"  Created {dc_count} district courts")

        # --- Probate Courts ---
        pc_count = 0
        for county, city in PROBATE_COUNTIES:
            court = Court(
                name=f"{county} County Probate Court",
                county=county,
                court_type=CourtType.PROBATE,
                city=city,
                state="MI",
                cms_type="JIS",
                is_efiling_enabled=True,
            )
            session.add(court)
            session.flush()

            for code, type_name, category, fee in PROBATE_CASE_TYPES:
                session.add(CaseType(
                    court_id=court.id,
                    code=code,
                    name=type_name,
                    category=category,
                    filing_fee_cents=fee,
                ))

            pc_count += 1

        print(f"  Created {pc_count} probate courts")

        # --- Court of Appeals (4 districts) ---
        for district in range(1, 5):
            court = Court(
                name=f"Michigan Court of Appeals - District {district}",
                county="Statewide",
                court_type=CourtType.COURT_OF_APPEALS,
                city=["Detroit", "Troy", "Grand Rapids", "Lansing"][district - 1],
                state="MI",
                cms_type="TrueFiling",
                is_efiling_enabled=True,
            )
            session.add(court)
            session.flush()

            for code, type_name, category, fee in APPEALS_CASE_TYPES:
                session.add(CaseType(
                    court_id=court.id,
                    code=code,
                    name=type_name,
                    category=category,
                    filing_fee_cents=fee,
                ))

        print("  Created 4 Court of Appeals districts")

        # --- Supreme Court ---
        court = Court(
            name="Michigan Supreme Court",
            county="Statewide",
            court_type=CourtType.SUPREME_COURT,
            city="Lansing",
            state="MI",
            cms_type="TrueFiling",
            is_efiling_enabled=True,
        )
        session.add(court)
        session.flush()

        for code, type_name, category, fee in APPEALS_CASE_TYPES:
            session.add(CaseType(
                court_id=court.id,
                code=code,
                name=type_name,
                category=category,
                filing_fee_cents=fee + 12500,  # Supreme Court fees are higher
            ))

        print("  Created Michigan Supreme Court")

        session.commit()

        total = session.query(Court).count()
        total_types = session.query(CaseType).count()
        total_reqs = session.query(FilingRequirement).count()
        print(f"\nSeed complete: {total} courts, {total_types} case types, {total_reqs} filing requirements")


if __name__ == "__main__":
    seed_database()
