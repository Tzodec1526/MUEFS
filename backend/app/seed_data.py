"""Seed data for Michigan Unified E-Filing System.

Populates the database with all Michigan courts, case types,
filing requirements, and demo users.

Usage: python -m app.seed_data
"""

import os
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

DATABASE_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://muefs:muefs_dev@localhost:5432/muefs",
)

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
    (11, ["Alger", "Luce", "Mackinac", "Schoolcraft"], "Munising"),
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

# Michigan District Courts (complete statewide coverage)
DISTRICT_COURTS = [
    # 1st District - Monroe County
    ("1st District Court", "Monroe", "Monroe"),
    # 2nd District - Lenawee & Hillsdale Counties
    ("2A District Court", "Lenawee", "Adrian"),
    ("2B District Court", "Hillsdale", "Hillsdale"),
    # 3rd District - Branch & St. Joseph Counties
    ("3A District Court", "Branch", "Coldwater"),
    ("3B District Court", "St. Joseph", "Centreville"),
    # 4th District - Cass & Berrien Counties
    ("4th District Court", "Cass", "Cassopolis"),
    # 5th District - Berrien County
    ("5th District Court", "Berrien", "St. Joseph"),
    # 6th District - Oakland County
    ("6th District Court", "Oakland", "Rochester"),  # Removed - merged
    # 7th District - Van Buren County
    ("7th District Court", "Van Buren", "Paw Paw"),
    # 8th District - Kalamazoo County
    ("8th District Court", "Kalamazoo", "Kalamazoo"),
    # 9th District - Kalamazoo County
    ("9th District Court", "Kalamazoo", "Portage"),
    # 10th District - Calhoun County
    ("10th District Court", "Calhoun", "Battle Creek"),
    # 12th District - Jackson County
    ("12th District Court", "Jackson", "Jackson"),
    # 13th District - Calhoun County (Albion/Marshall area)
    ("13th District Court", "Calhoun", "Marshall"),  # Removed per consolidation
    # 14th District - Washtenaw County
    ("14A District Court", "Washtenaw", "Ann Arbor"),
    ("14B District Court", "Washtenaw", "Ypsilanti"),
    # 15th District - Washtenaw County
    ("15th District Court", "Washtenaw", "Ann Arbor"),
    # 16th District - Livingston County
    ("16th District Court", "Livingston", "Howell"),
    # 17th District - Redford Township (Wayne County)
    ("17th District Court", "Wayne", "Redford"),
    # 18th District - City of Westland (Wayne County)
    ("18th District Court", "Wayne", "Westland"),
    # 19th District - City of Dearborn (Wayne County)
    ("19th District Court", "Wayne", "Dearborn"),
    # 20th District - Dearborn Heights (Wayne County)
    ("20th District Court", "Wayne", "Dearborn Heights"),
    # 21st District - Garden City (Wayne County)
    ("21st District Court", "Wayne", "Garden City"),
    # 22nd District - City of Inkster (Wayne County)
    ("22nd District Court", "Wayne", "Inkster"),
    # 23rd District - Taylor (Wayne County)
    ("23rd District Court", "Wayne", "Taylor"),
    # 24th District - Allen Park (Wayne County)
    ("24th District Court", "Wayne", "Allen Park"),
    # 25th District - Lincoln Park (Wayne County)
    ("25th District Court", "Wayne", "Lincoln Park"),
    # 27th District - Wyandotte (Wayne County)
    ("27th District Court", "Wayne", "Wyandotte"),
    # 28th District - Southgate (Wayne County)
    ("28th District Court", "Wayne", "Southgate"),
    # 29th District - Wayne (Wayne County)
    ("29th District Court", "Wayne", "Wayne"),
    # 30th District - Highland Park (Wayne County)
    ("30th District Court", "Wayne", "Highland Park"),
    # 31st District - Hamtramck (Wayne County)
    ("31st District Court", "Wayne", "Hamtramck"),
    # 32A District - Harper Woods (Wayne County)
    ("32A District Court", "Wayne", "Harper Woods"),
    # 33rd District - Woodhaven/Flat Rock/Rockwood (Wayne County)
    ("33rd District Court", "Wayne", "Woodhaven"),
    # 34th District - Romulus (Wayne County)
    ("34th District Court", "Wayne", "Romulus"),
    # 35th District - Plymouth/Northville/Canton (Wayne County)
    ("35th District Court", "Wayne", "Plymouth"),
    # 36th District - City of Detroit (Wayne County)
    ("36th District Court", "Wayne", "Detroit"),
    # 37th District - Warren (Macomb County)
    ("37th District Court", "Macomb", "Warren"),
    # 38th District - Eastpointe (Macomb County)
    ("38th District Court", "Macomb", "Eastpointe"),
    # 39th District - Roseville/Fraser (Macomb County)
    ("39th District Court", "Macomb", "Roseville"),
    # 40th District - St. Clair Shores (Macomb County)
    ("40th District Court", "Macomb", "St. Clair Shores"),
    # 41A District - Sterling Heights/Utica (Macomb County)
    ("41A District Court", "Macomb", "Sterling Heights"),
    # 41B District - Clinton Township/Mt. Clemens (Macomb County)
    ("41B District Court", "Macomb", "Clinton Township"),
    # 42-1 District - Romeo/Washington/Bruce/Armada (Macomb County)
    ("42-1 District Court", "Macomb", "Romeo"),
    # 42-2 District - New Baltimore/Chesterfield/Lenox (Macomb County)
    ("42-2 District Court", "Macomb", "New Baltimore"),
    # 43rd District - Hazel Park/Madison Heights/Ferndale (Oakland County)
    ("43rd District Court", "Oakland", "Hazel Park"),
    # 44th District - Royal Oak (Oakland County)
    ("44th District Court", "Oakland", "Royal Oak"),
    # 45A District - Berkley/Huntington Woods (Oakland County)
    ("45A District Court", "Oakland", "Berkley"),
    # 45B District - Oak Park (Oakland County)
    ("45B District Court", "Oakland", "Oak Park"),
    # 46th District - Southfield/Lathrup Village (Oakland County)
    ("46th District Court", "Oakland", "Southfield"),
    # 47th District - Farmington/Farmington Hills (Oakland County)
    ("47th District Court", "Oakland", "Farmington Hills"),
    # 48th District - Bloomfield Hills/Birmingham/Sylvan Lake (Oakland County)
    ("48th District Court", "Oakland", "Bloomfield Hills"),
    # 50th District - Pontiac (Oakland County)
    ("50th District Court", "Oakland", "Pontiac"),
    # 51st District - Waterford (Oakland County)
    ("51st District Court", "Oakland", "Waterford"),
    # 52-1 District - Novi/Walled Lake/Wixom/South Lyon (Oakland County)
    ("52-1 District Court", "Oakland", "Novi"),
    # 52-2 District - Clarkston/Ortonville (Oakland County)
    ("52-2 District Court", "Oakland", "Clarkston"),
    # 52-3 District - Rochester/Rochester Hills (Oakland County)
    ("52-3 District Court", "Oakland", "Rochester Hills"),
    # 52-4 District - Troy (Oakland County)
    ("52-4 District Court", "Oakland", "Troy"),
    # 53rd District - Howell (Livingston County) - same as 16th, skip duplicate
    # 54A District - Lansing (Ingham County)
    ("54A District Court", "Ingham", "Lansing"),
    # 54B District - East Lansing (Ingham County)
    ("54B District Court", "Ingham", "East Lansing"),
    # 55th District - Mason/Ingham County
    ("55th District Court", "Ingham", "Mason"),
    # 56A District - Eaton County
    ("56A District Court", "Eaton", "Charlotte"),
    # 56B District - Barry County
    ("56B District Court", "Barry", "Hastings"),
    # 57th District - Allegan County
    ("57th District Court", "Allegan", "Allegan"),
    # 58th District - Ottawa County
    ("58th District Court", "Ottawa", "Grand Haven"),
    # 59th District - Grandville/Walker (Kent County)
    ("59th District Court", "Kent", "Grandville"),
    # 60th District - Muskegon County
    ("60th District Court", "Muskegon", "Muskegon"),
    # 61st District - Grand Rapids (Kent County)
    ("61st District Court", "Kent", "Grand Rapids"),
    # 62A District - Wyoming/Byron Center (Kent County)
    ("62A District Court", "Kent", "Wyoming"),
    # 62B District - Kentwood/Lowell (Kent County)
    ("62B District Court", "Kent", "Kentwood"),
    # 63rd District - Grand Rapids/East Grand Rapids/Cascade (Kent County)
    ("63rd District Court", "Kent", "Grand Rapids"),
    # 64A District - Ionia County
    ("64A District Court", "Ionia", "Ionia"),
    # 64B District - Isabella County
    ("64B District Court", "Isabella", "Mount Pleasant"),
    # 65A District - Clinton County
    ("65A District Court", "Clinton", "St. Johns"),
    # 65B District - Gratiot County
    ("65B District Court", "Gratiot", "Ithaca"),
    # 66th District - Shiawassee County
    ("66th District Court", "Shiawassee", "Corunna"),
    # 67th District - Genesee County
    ("67th District Court", "Genesee", "Flint"),
    # 68th District - Genesee County
    ("68th District Court", "Genesee", "Flint"),
    # 69th District - St. Clair County
    ("69th District Court", "St. Clair", "Port Huron"),
    # 70th District - Saginaw County
    ("70th District Court", "Saginaw", "Saginaw"),
    # 71A District - Lapeer County
    ("71A District Court", "Lapeer", "Lapeer"),
    # 71B District - Tuscola County
    ("71B District Court", "Tuscola", "Caro"),
    # 72nd District - St. Clair County (Marine City/Port Huron area)
    ("72nd District Court", "St. Clair", "Marine City"),
    # 73rd District - Saginaw County
    ("73rd District Court", "Saginaw", "Saginaw"),
    # 74th District - Bay County
    ("74th District Court", "Bay", "Bay City"),
    # 75th District - Midland County
    ("75th District Court", "Midland", "Midland"),
    # 76th District - Clare & Gladwin Counties
    ("76th District Court", "Clare", "Harrison"),
    # 77th District - Mecosta & Osceola Counties
    ("77th District Court", "Mecosta", "Big Rapids"),
    # 78th District - Newaygo County
    ("78th District Court", "Newaygo", "White Cloud"),
    # 79th District - Mason & Lake Counties
    ("79th District Court", "Mason", "Ludington"),
    # 80th District - Wexford & Missaukee Counties
    ("80th District Court", "Wexford", "Cadillac"),
    # 81st District - Alcona, Arenac, Iosco, Oscoda Counties
    ("81st District Court", "Iosco", "Tawas City"),
    # 82nd District - Ogemaw & Roscommon Counties
    ("82nd District Court", "Ogemaw", "West Branch"),
    # 83rd District - Huron & Sanilac Counties
    ("83rd District Court", "Huron", "Bad Axe"),
    # 84th District - Manistee & Benzie Counties
    ("84th District Court", "Manistee", "Manistee"),
    # 85th District - Leelanau & Grand Traverse Counties
    ("85th District Court", "Grand Traverse", "Traverse City"),
    # 86th District - Antrim & Grand Traverse Counties
    ("86th District Court", "Grand Traverse", "Traverse City"),
    # 87th District - Kalkaska, Crawford, Otsego Counties
    ("87th District Court", "Otsego", "Gaylord"),
    # 88th District - Alpena & Montmorency Counties
    ("88th District Court", "Alpena", "Alpena"),
    # 89th District - Cheboygan & Presque Isle Counties
    ("89th District Court", "Cheboygan", "Cheboygan"),
    # 90th District - Emmet & Charlevoix Counties
    ("90th District Court", "Emmet", "Petoskey"),
    # 91st District - Chippewa County
    ("91st District Court", "Chippewa", "Sault Ste. Marie"),
    # 92nd District - Luce & Mackinac Counties
    ("92nd District Court", "Luce", "Newberry"),
    # 93rd District - Alger & Schoolcraft Counties
    ("93rd District Court", "Alger", "Munising"),
    # 94th District - Delta & Menominee Counties
    ("94th District Court", "Delta", "Escanaba"),
    # 95A District - Dickinson County
    ("95A District Court", "Dickinson", "Iron Mountain"),
    # 95B District - Menominee County
    ("95B District Court", "Menominee", "Menominee"),
    # 96th District - Marquette County
    ("96th District Court", "Marquette", "Marquette"),
    # 97th District - Baraga, Houghton, Keweenaw Counties
    ("97th District Court", "Houghton", "Houghton"),
    # 98th District - Iron, Gogebic, Ontonagon Counties
    ("98th District Court", "Gogebic", "Bessemer"),
]

# Michigan Probate Courts (all 83 counties)
PROBATE_COUNTIES = [
    ("Alcona", "Harrisville"),
    ("Alger", "Munising"),
    ("Allegan", "Allegan"),
    ("Alpena", "Alpena"),
    ("Antrim", "Bellaire"),
    ("Arenac", "Standish"),
    ("Baraga", "L'Anse"),
    ("Barry", "Hastings"),
    ("Bay", "Bay City"),
    ("Benzie", "Beulah"),
    ("Berrien", "St. Joseph"),
    ("Branch", "Coldwater"),
    ("Calhoun", "Battle Creek"),
    ("Cass", "Cassopolis"),
    ("Charlevoix", "Charlevoix"),
    ("Cheboygan", "Cheboygan"),
    ("Chippewa", "Sault Ste. Marie"),
    ("Clare", "Harrison"),
    ("Clinton", "St. Johns"),
    ("Crawford", "Grayling"),
    ("Delta", "Escanaba"),
    ("Dickinson", "Iron Mountain"),
    ("Eaton", "Charlotte"),
    ("Emmet", "Petoskey"),
    ("Genesee", "Flint"),
    ("Gladwin", "Gladwin"),
    ("Gogebic", "Bessemer"),
    ("Grand Traverse", "Traverse City"),
    ("Gratiot", "Ithaca"),
    ("Hillsdale", "Hillsdale"),
    ("Houghton", "Houghton"),
    ("Huron", "Bad Axe"),
    ("Ingham", "Lansing"),
    ("Ionia", "Ionia"),
    ("Iosco", "Tawas City"),
    ("Iron", "Crystal Falls"),
    ("Isabella", "Mount Pleasant"),
    ("Jackson", "Jackson"),
    ("Kalamazoo", "Kalamazoo"),
    ("Kalkaska", "Kalkaska"),
    ("Kent", "Grand Rapids"),
    ("Keweenaw", "Eagle River"),
    ("Lake", "Baldwin"),
    ("Lapeer", "Lapeer"),
    ("Leelanau", "Suttons Bay"),
    ("Lenawee", "Adrian"),
    ("Livingston", "Howell"),
    ("Luce", "Newberry"),
    ("Mackinac", "St. Ignace"),
    ("Macomb", "Mount Clemens"),
    ("Manistee", "Manistee"),
    ("Marquette", "Marquette"),
    ("Mason", "Ludington"),
    ("Mecosta", "Big Rapids"),
    ("Menominee", "Menominee"),
    ("Midland", "Midland"),
    ("Missaukee", "Lake City"),
    ("Monroe", "Monroe"),
    ("Montcalm", "Stanton"),
    ("Montmorency", "Atlanta"),
    ("Muskegon", "Muskegon"),
    ("Newaygo", "White Cloud"),
    ("Oakland", "Pontiac"),
    ("Oceana", "Hart"),
    ("Ogemaw", "West Branch"),
    ("Ontonagon", "Ontonagon"),
    ("Osceola", "Reed City"),
    ("Oscoda", "Mio"),
    ("Otsego", "Gaylord"),
    ("Ottawa", "Grand Haven"),
    ("Presque Isle", "Rogers City"),
    ("Roscommon", "Roscommon"),
    ("Saginaw", "Saginaw"),
    ("Sanilac", "Sandusky"),
    ("Schoolcraft", "Manistique"),
    ("Shiawassee", "Corunna"),
    ("St. Clair", "Port Huron"),
    ("St. Joseph", "Centreville"),
    ("Tuscola", "Caro"),
    ("Van Buren", "Paw Paw"),
    ("Washtenaw", "Ann Arbor"),
    ("Wayne", "Detroit"),
    ("Wexford", "Cadillac"),
]

# Common case types
# Circuit courts have general jurisdiction (no small claims - those go to district)
CIRCUIT_CIVIL_CASE_TYPES = [
    ("CIV-GEN", "Civil - General", CaseCategory.CIVIL, 17500),
    ("CIV-TORT", "Civil - Tort", CaseCategory.CIVIL, 17500),
    ("CIV-CONT", "Civil - Contract", CaseCategory.CIVIL, 17500),
    ("CIV-PROP", "Civil - Property", CaseCategory.CIVIL, 17500),
    ("CIV-COND", "Civil - Condemnation", CaseCategory.CIVIL, 17500),
    ("CIV-SUBP", "Domesticating Subpoena - MI Uniform Depositions Act", CaseCategory.CIVIL, 17500),
]

# District courts have limited jurisdiction (includes small claims)
DISTRICT_CIVIL_CASE_TYPES = [
    ("CIV-GEN", "Civil - General", CaseCategory.CIVIL, 17500),
    ("CIV-TORT", "Civil - Tort", CaseCategory.CIVIL, 17500),
    ("CIV-CONT", "Civil - Contract", CaseCategory.CIVIL, 17500),
    ("CIV-PROP", "Civil - Property", CaseCategory.CIVIL, 17500),
    ("SM-CLM", "Small Claims", CaseCategory.SMALL_CLAIMS, 3000),
    ("CIV-SUBP", "Domesticating Subpoena - MI Uniform Depositions Act", CaseCategory.CIVIL, 17500),
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

# Court of Claims case types (MCL 600.6401 et seq.)
COURT_OF_CLAIMS_CASE_TYPES = [
    ("COC-TORT", "Tort Claim Against State of Michigan", CaseCategory.CIVIL, 17500),
    ("COC-CONT", "Contract Claim Against State of Michigan", CaseCategory.CIVIL, 17500),
    ("COC-CONST", "Constitutional Claim Against State", CaseCategory.CIVIL, 17500),
    ("COC-TAX", "Tax-Related Claim Against State", CaseCategory.CIVIL, 17500),
    ("COC-HWY", "Highway Defect Claim (MCL 691.1402)", CaseCategory.CIVIL, 17500),
    ("COC-PROP", "Property/Takings Claim Against State", CaseCategory.CIVIL, 17500),
    ("COC-APPREV", "Appeal of Administrative Agency Decision", CaseCategory.CIVIL, 17500),
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

# Filing requirements for domesticating subpoena (Michigan Uniform Depositions Act, MCL 600.2163a)
SUBPOENA_FILING_REQUIREMENTS = [
    ("SUBPOENA", True, "Out-of-State Subpoena (authenticated copy)", "MCL 600.2163a", None,
     "Must be issued by court of record in another state"),
    ("COVER_LETTER", True, "Cover Letter / Request to Domesticate", None, None,
     "Letter requesting issuance of Michigan subpoena"),
    ("AFFIDAVIT", False, "Affidavit of Compliance", None, None, None),
    ("PROPOSED_SUBP", True, "Proposed Michigan Subpoena", "MCR 2.506", None,
     "Michigan subpoena incorporating terms of out-of-state subpoena"),
    ("FILING_FEE", True, "Filing Fee", None, None, None),
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

            # Add case types (circuit courts: no small claims)
            for code, type_name, category, fee in CIRCUIT_CIVIL_CASE_TYPES + FAMILY_CASE_TYPES + CRIMINAL_CASE_TYPES:
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

            # Add filing requirements for domesticating subpoena
            subp_ct = session.query(CaseType).filter_by(
                court_id=court.id, code="CIV-SUBP"
            ).first()
            if subp_ct:
                for doc_code, required, desc, mcr, page_limit, notes in SUBPOENA_FILING_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=subp_ct.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
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

            for code, type_name, category, fee in DISTRICT_CIVIL_CASE_TYPES + CRIMINAL_CASE_TYPES:
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

        # --- Court of Claims ---
        # Statewide jurisdiction for claims against State of Michigan
        # Administratively part of 30th Circuit Court (Ingham County)
        # Per MCL 600.6401 et seq.
        coc = Court(
            name="Michigan Court of Claims",
            county="Ingham",
            court_type=CourtType.COURT_OF_CLAIMS,
            division="Statewide Jurisdiction",
            city="Lansing",
            state="MI",
            cms_type="JIS",
            is_efiling_enabled=True,
        )
        session.add(coc)
        session.flush()

        for code, type_name, category, fee in COURT_OF_CLAIMS_CASE_TYPES:
            session.add(CaseType(
                court_id=coc.id,
                code=code,
                name=type_name,
                category=category,
                filing_fee_cents=fee,
            ))

        print("  Created Michigan Court of Claims")

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

        # --- Demo Cases & Filings for frontend testing ---
        from app.models.case import Case, CaseParticipant, CaseStatus, ParticipantRole
        from app.models.filing import FilingEnvelope, FilingDocument, FilingStatus
        from app.models.user import FavoriteCase
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        attorney = users[0]  # Jane Doe, P12345
        clerk_user = users[1]  # Robert Johnson

        # Get the 3rd Circuit Court (Wayne County - Detroit)
        wayne_circuit = session.query(Court).filter_by(
            name="3rd Circuit Court"
        ).first()

        if wayne_circuit:
            wayne_civil = session.query(CaseType).filter_by(
                court_id=wayne_circuit.id, code="CIV-GEN"
            ).first()
            wayne_tort = session.query(CaseType).filter_by(
                court_id=wayne_circuit.id, code="CIV-TORT"
            ).first()
            wayne_contract = session.query(CaseType).filter_by(
                court_id=wayne_circuit.id, code="CIV-CONT"
            ).first()
            wayne_divorce = session.query(CaseType).filter_by(
                court_id=wayne_circuit.id, code="FAM-DIV"
            ).first()
            wayne_subp = session.query(CaseType).filter_by(
                court_id=wayne_circuit.id, code="CIV-SUBP"
            ).first()

            # --- Case 1: Active breach of contract case ---
            case1 = Case(
                court_id=wayne_circuit.id,
                case_number=f"MI-{wayne_circuit.id}-2025-000001",
                case_type_id=wayne_contract.id if wayne_contract else wayne_civil.id,
                title="Johnson v. Smith Industries LLC",
                status=CaseStatus.OPEN,
                filed_date=now,
            )
            session.add(case1)
            session.flush()

            session.add(CaseParticipant(
                case_id=case1.id, role=ParticipantRole.PLAINTIFF,
                party_name="Robert Johnson", contact_email="rjohnson@example.com",
            ))
            session.add(CaseParticipant(
                case_id=case1.id, role=ParticipantRole.DEFENDANT,
                party_name="Smith Industries LLC", contact_email="legal@smithindustries.com",
            ))
            session.add(CaseParticipant(
                case_id=case1.id, user_id=attorney.id,
                role=ParticipantRole.ATTORNEY_PLAINTIFF,
                party_name="Jane Doe", attorney_bar_number="P12345",
            ))

            # Initial complaint filing (accepted)
            filing1 = FilingEnvelope(
                court_id=wayne_circuit.id, case_id=case1.id,
                case_type_id=wayne_contract.id if wayne_contract else wayne_civil.id,
                filer_id=attorney.id,
                case_title="Johnson v. Smith Industries LLC",
                filing_description="Initial complaint for breach of contract - failure to deliver goods per Purchase Order #2024-8891",
                status=FilingStatus.ACCEPTED,
                submitted_at=now, reviewed_at=now, reviewer_id=clerk_user.id,
            )
            session.add(filing1)
            session.flush()
            session.add(FilingDocument(
                envelope_id=filing1.id, document_type_code="COMPLAINT",
                title="Complaint for Breach of Contract",
                file_key="demo/case1/complaint.pdf", file_size_bytes=45056,
                mime_type="application/pdf", sha256_hash="demo_hash_001",
                page_count=12, is_text_searchable=True,
            ))

            # Motion filing (submitted, pending review)
            filing1_motion = FilingEnvelope(
                court_id=wayne_circuit.id, case_id=case1.id,
                case_type_id=wayne_contract.id if wayne_contract else wayne_civil.id,
                filer_id=attorney.id,
                case_title="Johnson v. Smith Industries LLC",
                filing_description="Motion for Summary Disposition under MCR 2.116(C)(10) - No genuine issue of material fact",
                status=FilingStatus.SUBMITTED,
                submitted_at=now,
            )
            session.add(filing1_motion)
            session.flush()
            session.add(FilingDocument(
                envelope_id=filing1_motion.id, document_type_code="MOTION",
                title="Motion for Summary Disposition",
                file_key="demo/case1/motion_sd.pdf", file_size_bytes=28672,
                mime_type="application/pdf", sha256_hash="demo_hash_002",
                page_count=8, is_text_searchable=True,
            ))
            session.add(FilingDocument(
                envelope_id=filing1_motion.id, document_type_code="BRIEF",
                title="Brief in Support of Motion for Summary Disposition",
                file_key="demo/case1/brief_sd.pdf", file_size_bytes=61440,
                mime_type="application/pdf", sha256_hash="demo_hash_003",
                page_count=18, is_text_searchable=True,
            ))

            # --- Case 2: Personal injury tort case ---
            case2 = Case(
                court_id=wayne_circuit.id,
                case_number=f"MI-{wayne_circuit.id}-2025-000002",
                case_type_id=wayne_tort.id if wayne_tort else wayne_civil.id,
                title="Williams v. City of Detroit",
                status=CaseStatus.OPEN,
                filed_date=now,
            )
            session.add(case2)
            session.flush()

            session.add(CaseParticipant(
                case_id=case2.id, role=ParticipantRole.PLAINTIFF,
                party_name="Maria Williams",
            ))
            session.add(CaseParticipant(
                case_id=case2.id, role=ParticipantRole.DEFENDANT,
                party_name="City of Detroit",
            ))
            session.add(CaseParticipant(
                case_id=case2.id, user_id=attorney.id,
                role=ParticipantRole.ATTORNEY_PLAINTIFF,
                party_name="Jane Doe", attorney_bar_number="P12345",
            ))

            filing2 = FilingEnvelope(
                court_id=wayne_circuit.id, case_id=case2.id,
                case_type_id=wayne_tort.id if wayne_tort else wayne_civil.id,
                filer_id=attorney.id,
                case_title="Williams v. City of Detroit",
                filing_description="Complaint for personal injury - sidewalk defect on Michigan Ave",
                status=FilingStatus.ACCEPTED,
                submitted_at=now, reviewed_at=now, reviewer_id=clerk_user.id,
            )
            session.add(filing2)
            session.flush()
            session.add(FilingDocument(
                envelope_id=filing2.id, document_type_code="COMPLAINT",
                title="Complaint for Personal Injury",
                file_key="demo/case2/complaint.pdf", file_size_bytes=38912,
                mime_type="application/pdf", sha256_hash="demo_hash_004",
                page_count=10, is_text_searchable=True,
            ))

            # --- Case 3: Divorce case ---
            if wayne_divorce:
                case3 = Case(
                    court_id=wayne_circuit.id,
                    case_number=f"MI-{wayne_circuit.id}-2025-000003",
                    case_type_id=wayne_divorce.id,
                    title="Thompson v. Thompson",
                    status=CaseStatus.OPEN,
                    filed_date=now,
                )
                session.add(case3)
                session.flush()

                session.add(CaseParticipant(
                    case_id=case3.id, role=ParticipantRole.PETITIONER,
                    party_name="Sarah Thompson",
                ))
                session.add(CaseParticipant(
                    case_id=case3.id, role=ParticipantRole.RESPONDENT,
                    party_name="Michael Thompson",
                ))

                filing3 = FilingEnvelope(
                    court_id=wayne_circuit.id, case_id=case3.id,
                    case_type_id=wayne_divorce.id,
                    filer_id=attorney.id,
                    case_title="Thompson v. Thompson",
                    filing_description="Complaint for Divorce",
                    status=FilingStatus.ACCEPTED,
                    submitted_at=now, reviewed_at=now, reviewer_id=clerk_user.id,
                )
                session.add(filing3)
                session.flush()
                session.add(FilingDocument(
                    envelope_id=filing3.id, document_type_code="COMPLAINT",
                    title="Complaint for Divorce",
                    file_key="demo/case3/divorce_complaint.pdf", file_size_bytes=22528,
                    mime_type="application/pdf", sha256_hash="demo_hash_005",
                    page_count=6, is_text_searchable=True,
                ))

            # --- Case 4: Domesticating subpoena ---
            if wayne_subp:
                case4 = Case(
                    court_id=wayne_circuit.id,
                    case_number=f"MI-{wayne_circuit.id}-2025-000004",
                    case_type_id=wayne_subp.id,
                    title="In re: Subpoena from State of Ohio, Case No. CV-2025-4412",
                    status=CaseStatus.OPEN,
                    filed_date=now,
                )
                session.add(case4)
                session.flush()

                filing4 = FilingEnvelope(
                    court_id=wayne_circuit.id, case_id=case4.id,
                    case_type_id=wayne_subp.id,
                    filer_id=attorney.id,
                    case_title="In re: Subpoena from State of Ohio, Case No. CV-2025-4412",
                    filing_description="Domesticating out-of-state subpoena per Michigan Uniform Depositions Act (MCL 600.2163a)",
                    status=FilingStatus.SUBMITTED,
                    submitted_at=now,
                )
                session.add(filing4)
                session.flush()
                session.add(FilingDocument(
                    envelope_id=filing4.id, document_type_code="SUBPOENA",
                    title="Ohio Subpoena - Authenticated Copy",
                    file_key="demo/case4/ohio_subpoena.pdf", file_size_bytes=15360,
                    mime_type="application/pdf", sha256_hash="demo_hash_006",
                    page_count=4, is_text_searchable=True,
                ))
                session.add(FilingDocument(
                    envelope_id=filing4.id, document_type_code="PROPOSED_SUBP",
                    title="Proposed Michigan Subpoena",
                    file_key="demo/case4/proposed_mi_subpoena.pdf", file_size_bytes=12288,
                    mime_type="application/pdf", sha256_hash="demo_hash_007",
                    page_count=3, is_text_searchable=True,
                ))

            # --- Case 5: Rejected filing (returned for correction) ---
            filing5 = FilingEnvelope(
                court_id=wayne_circuit.id,
                case_type_id=wayne_civil.id,
                filer_id=attorney.id,
                case_title="Anderson v. Metro Health Systems",
                filing_description="Complaint for medical malpractice",
                status=FilingStatus.RETURNED,
                submitted_at=now, reviewed_at=now, reviewer_id=clerk_user.id,
                rejection_reason="Missing Affidavit of Merit required by MCL 600.2912d for medical malpractice cases. Please attach and resubmit.",
            )
            session.add(filing5)
            session.flush()
            session.add(FilingDocument(
                envelope_id=filing5.id, document_type_code="COMPLAINT",
                title="Complaint for Medical Malpractice",
                file_key="demo/case5/complaint.pdf", file_size_bytes=51200,
                mime_type="application/pdf", sha256_hash="demo_hash_008",
                page_count=15, is_text_searchable=True,
            ))

            # Auto-favorite case 1 for the demo attorney
            session.add(FavoriteCase(
                user_id=attorney.id, case_id=case1.id,
                notes="Key breach of contract case - motion for SD pending",
            ))

            demo_cases = session.query(Case).count()
            demo_filings = session.query(FilingEnvelope).count()
            print(f"  Created {demo_cases} demo cases with {demo_filings} filings")

        session.commit()

        total = session.query(Court).count()
        total_types = session.query(CaseType).count()
        total_reqs = session.query(FilingRequirement).count()
        print(f"\nSeed complete: {total} courts, {total_types} case types, {total_reqs} filing requirements")


if __name__ == "__main__":
    seed_database()
