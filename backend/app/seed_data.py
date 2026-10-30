import asyncio
from datetime import UTC, datetime

from sqlalchemy import Connection, Engine, create_engine, func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session

from alembic import command
from app.config import settings
from app.database import Base
from app.demo.documents import sample_document
from app.demo.schema import alembic_config, prepare_demo_connection
from app.models.court import (
    CaseCategory,
    CaseType,
    Court,
    CourtType,
    FilingChecklist,
    FilingRequirement,
)
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import document_service


def _ordinal(n: int) -> str:
    if n % 100 in (11, 12, 13):
        return f"{n}th"
    return f"{n}{({1: 'st', 2: 'nd', 3: 'rd'}).get(n % 10, 'th')}"

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

DISTRICT_COURTS = [
    ("1st District Court", "Monroe", "Monroe"),
    ("2A District Court", "Lenawee", "Adrian"),
    ("2B District Court", "Hillsdale", "Hillsdale"),
    ("3A District Court", "Branch", "Coldwater"),
    ("3B District Court", "St. Joseph", "Centreville"),
    ("4th District Court", "Cass", "Cassopolis"),
    ("5th District Court", "Berrien", "St. Joseph"),
    ("7th District Court", "Van Buren", "Paw Paw"),
    ("8th District Court", "Kalamazoo", "Kalamazoo"),
    ("9th District Court", "Kalamazoo", "Portage"),
    ("10th District Court", "Calhoun", "Battle Creek"),
    ("12th District Court", "Jackson", "Jackson"),
    ("14A District Court", "Washtenaw", "Ann Arbor"),
    ("14B District Court", "Washtenaw", "Ypsilanti"),
    ("15th District Court", "Washtenaw", "Ann Arbor"),
    ("16th District Court", "Wayne", "Livonia"),
    ("17th District Court", "Wayne", "Redford"),
    ("18th District Court", "Wayne", "Westland"),
    ("19th District Court", "Wayne", "Dearborn"),
    ("20th District Court", "Wayne", "Dearborn Heights"),
    ("21st District Court", "Wayne", "Garden City"),
    ("22nd District Court", "Wayne", "Inkster"),
    ("23rd District Court", "Wayne", "Taylor"),
    ("24th District Court", "Wayne", "Allen Park"),
    ("25th District Court", "Wayne", "Lincoln Park"),
    ("27th District Court", "Wayne", "Wyandotte"),
    ("28th District Court", "Wayne", "Southgate"),
    ("29th District Court", "Wayne", "Wayne"),
    ("30th District Court", "Wayne", "Highland Park"),
    ("31st District Court", "Wayne", "Hamtramck"),
    ("32A District Court", "Wayne", "Harper Woods"),
    ("33rd District Court", "Wayne", "Woodhaven"),
    ("34th District Court", "Wayne", "Romulus"),
    ("35th District Court", "Wayne", "Plymouth"),
    ("36th District Court", "Wayne", "Detroit"),
    ("37th District Court", "Macomb", "Warren"),
    ("38th District Court", "Macomb", "Eastpointe"),
    ("39th District Court", "Macomb", "Roseville"),
    ("40th District Court", "Macomb", "St. Clair Shores"),
    ("41A District Court", "Macomb", "Sterling Heights"),
    ("41B District Court", "Macomb", "Clinton Township"),
    ("42-1 District Court", "Macomb", "Romeo"),
    ("42-2 District Court", "Macomb", "New Baltimore"),
    ("43rd District Court", "Oakland", "Hazel Park"),
    ("44th District Court", "Oakland", "Royal Oak"),
    ("45A District Court", "Oakland", "Berkley"),
    ("45B District Court", "Oakland", "Oak Park"),
    ("46th District Court", "Oakland", "Southfield"),
    ("47th District Court", "Oakland", "Farmington Hills"),
    ("48th District Court", "Oakland", "Bloomfield Hills"),
    ("50th District Court", "Oakland", "Pontiac"),
    ("51st District Court", "Oakland", "Waterford"),
    ("52-1 District Court", "Oakland", "Novi"),
    ("52-2 District Court", "Oakland", "Clarkston"),
    ("52-3 District Court", "Oakland", "Rochester Hills"),
    ("52-4 District Court", "Oakland", "Troy"),
    ("53rd District Court", "Livingston", "Howell"),
    ("54A District Court", "Ingham", "Lansing"),
    ("54B District Court", "Ingham", "East Lansing"),
    ("55th District Court", "Ingham", "Mason"),
    ("56A District Court", "Eaton", "Charlotte"),
    ("56B District Court", "Barry", "Hastings"),
    ("57th District Court", "Allegan", "Allegan"),
    ("58th District Court", "Ottawa", "Grand Haven"),
    ("59th District Court", "Kent", "Grandville"),
    ("60th District Court", "Muskegon", "Muskegon"),
    ("61st District Court", "Kent", "Grand Rapids"),
    ("62A District Court", "Kent", "Wyoming"),
    ("62B District Court", "Kent", "Kentwood"),
    ("63rd District Court", "Kent", "Grand Rapids"),
    ("64A District Court", "Ionia", "Ionia"),
    ("64B District Court", "Isabella", "Mount Pleasant"),
    ("65A District Court", "Clinton", "St. Johns"),
    ("65B District Court", "Gratiot", "Ithaca"),
    ("66th District Court", "Shiawassee", "Corunna"),
    ("67th District Court", "Genesee", "Flint"),
    ("68th District Court", "Genesee", "Flint"),
    ("69th District Court", "St. Clair", "Port Huron"),
    ("70th District Court", "Saginaw", "Saginaw"),
    ("71A District Court", "Lapeer", "Lapeer"),
    ("71B District Court", "Tuscola", "Caro"),
    ("72nd District Court", "St. Clair", "Marine City"),
    ("73rd District Court", "Saginaw", "Saginaw"),
    ("74th District Court", "Bay", "Bay City"),
    ("75th District Court", "Midland", "Midland"),
    ("76th District Court", "Clare", "Harrison"),
    ("77th District Court", "Mecosta", "Big Rapids"),
    ("78th District Court", "Newaygo", "White Cloud"),
    ("79th District Court", "Mason", "Ludington"),
    ("80th District Court", "Wexford", "Cadillac"),
    ("81st District Court", "Iosco", "Tawas City"),
    ("82nd District Court", "Ogemaw", "West Branch"),
    ("83rd District Court", "Huron", "Bad Axe"),
    ("84th District Court", "Manistee", "Manistee"),
    ("85th District Court", "Grand Traverse", "Traverse City"),
    ("86th District Court", "Grand Traverse", "Traverse City"),
    ("87th District Court", "Otsego", "Gaylord"),
    ("88th District Court", "Alpena", "Alpena"),
    ("89th District Court", "Cheboygan", "Cheboygan"),
    ("90th District Court", "Emmet", "Petoskey"),
    ("91st District Court", "Chippewa", "Sault Ste. Marie"),
    ("92nd District Court", "Luce", "Newberry"),
    ("93rd District Court", "Alger", "Munising"),
    ("94th District Court", "Delta", "Escanaba"),
    ("95A District Court", "Dickinson", "Iron Mountain"),
    ("95B District Court", "Menominee", "Menominee"),
    ("96th District Court", "Marquette", "Marquette"),
    ("97th District Court", "Houghton", "Houghton"),
    ("98th District Court", "Gogebic", "Bessemer"),
]

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

CIRCUIT_CIVIL_CASE_TYPES = [
    ("CIV-GEN", "Civil - General", CaseCategory.CIVIL, 15000),
    ("CIV-TORT", "Civil - Tort", CaseCategory.CIVIL, 15000),
    ("CIV-CONT", "Civil - Contract", CaseCategory.CIVIL, 15000),
    ("CIV-PROP", "Civil - Property", CaseCategory.CIVIL, 15000),
    ("CIV-COND", "Civil - Condemnation", CaseCategory.CIVIL, 15000),
    ("CIV-BUS", "Business Court (MCL 600.8031 et seq.)", CaseCategory.CIVIL, 15000),
    ("CIV-GARN", "Garnishment", CaseCategory.CIVIL, 1500),
    ("CIR-APP", "Appeal from District/Probate/Agency", CaseCategory.APPEALS, 15000),
    ("CIV-SUBP", "Domesticating Subpoena - Uniform Interstate Depositions and Discovery Act", CaseCategory.CIVIL, 15000),
]

DISTRICT_CIVIL_CASE_TYPES = [
    ("CIV-GEN", "Civil - General", CaseCategory.CIVIL, 15000),
    ("CIV-TORT", "Civil - Tort", CaseCategory.CIVIL, 15000),
    ("CIV-CONT", "Civil - Contract", CaseCategory.CIVIL, 15000),
    ("CIV-PROP", "Civil - Property", CaseCategory.CIVIL, 15000),
    ("LT-SP", "Landlord-Tenant / Summary Proceedings", CaseCategory.CIVIL, 4500),
    ("SM-CLM", "Small Claims (up to $7,000)", CaseCategory.SMALL_CLAIMS, 4500),
    ("CIV-GARN", "Garnishment", CaseCategory.CIVIL, 1500),
    ("CIV-SUBP", "Domesticating Subpoena - Uniform Interstate Depositions and Discovery Act", CaseCategory.CIVIL, 15000),
]

FAMILY_CASE_TYPES = [
    ("FAM-DIV", "Divorce/Dissolution", CaseCategory.FAMILY, 15000),
    ("FAM-CUST", "Custody", CaseCategory.FAMILY, 15000),
    ("FAM-SUP", "Child Support", CaseCategory.FAMILY, 15000),
    ("FAM-PPO", "Personal Protection Order", CaseCategory.FAMILY, 0),
    ("FAM-ADPT", "Adoption", CaseCategory.FAMILY, 15000),
]

CRIMINAL_CASE_TYPES = [
    ("CR-FEL", "Criminal - Felony", CaseCategory.CRIMINAL, 0),
    ("CR-MISD", "Criminal - Misdemeanor", CaseCategory.CRIMINAL, 0),
    ("TR-CIV", "Traffic - Civil Infraction", CaseCategory.TRAFFIC, 0),
]

PROBATE_CASE_TYPES = [
    ("PR-EST", "Probate - Estate", CaseCategory.PROBATE, 15000),
    ("PR-GRDN", "Probate - Guardianship", CaseCategory.PROBATE, 15000),
    ("PR-CNSRV", "Probate - Conservatorship", CaseCategory.PROBATE, 15000),
    ("PR-TRUST", "Probate - Trust", CaseCategory.PROBATE, 15000),
    ("PR-MI", "Probate - Mental Health (Civil Commitment)", CaseCategory.PROBATE, 0),
]

COURT_OF_CLAIMS_CASE_TYPES = [
    ("COC-TORT", "Tort Claim Against State of Michigan", CaseCategory.CIVIL, 15000),
    ("COC-CONT", "Contract Claim Against State of Michigan", CaseCategory.CIVIL, 15000),
    ("COC-CONST", "Constitutional Claim Against State", CaseCategory.CIVIL, 15000),
    ("COC-TAX", "Tax-Related Claim Against State", CaseCategory.CIVIL, 15000),
    ("COC-HWY", "Highway Defect Claim (MCL 691.1402)", CaseCategory.CIVIL, 15000),
    ("COC-PROP", "Property/Takings Claim Against State", CaseCategory.CIVIL, 15000),
    ("COC-APPREV", "Appeal of Administrative Agency Decision", CaseCategory.CIVIL, 15000),
]

APPEALS_CASE_TYPES = [
    ("APP-CIV", "Appeal - Civil", CaseCategory.APPEALS, 37500),
    ("APP-CR", "Appeal - Criminal", CaseCategory.APPEALS, 37500),
    ("APP-FAM", "Appeal - Family", CaseCategory.APPEALS, 37500),
]

CIVIL_FILING_REQUIREMENTS = [
    ("COMPLAINT", True, "Complaint", "MCR 2.111", None, None),
    ("SUMMONS", True, "Summons (SCAO Form MC 01)", "MCR 2.102", None, None),
    ("PROOF_SERVICE", False, "Proof of Service", "MCR 2.104", None, None),
    ("EXHIBIT", False, "Exhibits", None, None, "Attach separately; label clearly"),
    ("JURY_DEMAND", False, "Jury Demand", "MCR 2.508", None, None),
]

SUBPOENA_FILING_REQUIREMENTS = [
    ("SUBPOENA", True, "Out-of-State Subpoena (authenticated copy)", "MCL 600.2201 et seq.", None,
     "Must be issued by court of record in another state"),
    ("COVER_LETTER", True, "Cover Letter / Request to Domesticate", None, None,
     "Letter requesting issuance of Michigan subpoena"),
    ("AFFIDAVIT", False, "Affidavit of Compliance", None, None, None),
    ("PROPOSED_SUBP", True, "Proposed Michigan Subpoena", "MCR 2.506", None,
     "Michigan subpoena incorporating terms of out-of-state subpoena"),
    ("FILING_FEE", True, "Filing Fee", None, None, None),
]

MOTION_FILING_REQUIREMENTS = [
    ("MOTION", True, "Motion", "MCR 2.119", 20, "Brief must not exceed 20 pages"),
    ("BRIEF_SUPPORT", False, "Brief in Support", "MCR 2.119(A)(2)", 20, "May be combined with the motion as a single document; a separate brief is not required to file."),
    ("PROPOSED_ORDER", False, "Proposed Order", "MCR 2.602", None, None),
    ("NOT_HEARING", False, "Notice of Hearing", "MCR 2.119(C)", None, "Must be served at least 9 days before hearing"),
    ("DISC_CERT_GF", False, "Certification of Good Faith Effort (discovery motions)", "MCR 2.313(A)(5)", None, "Recommended best practice. MCR 2.313(A)(5) makes a good-faith effort to resolve the dispute a factor in awarding motion expenses, not a required filing. A motion to compel a non-party subpoena must include the subpoena and proof of service under MCR 2.313(A)(2)(c)."),
]

DISTRICT_CIVIL_REQUIREMENTS = [
    ("COMPLAINT", True, "Complaint", "MCR 2.111", None, None),
    ("SUMMONS", True, "Summons (SCAO Form MC 01)", "MCR 2.102", None, None),
    ("PROOF_SERVICE", False, "Proof of Service", "MCR 2.104", None, None),
    ("EXHIBIT", False, "Exhibits", None, None, "Attach separately; label clearly"),
]

SMALL_CLAIMS_REQUIREMENTS = [
    ("SM_AFFIDAVIT", True, "Affidavit and Claim (SCAO Form DC 84)", "MCR 4.302", None, None),
    ("EXHIBIT", False, "Supporting Documents/Evidence", None, None, None),
]

FAMILY_FILING_REQUIREMENTS = [
    ("COMPLAINT", True, "Complaint for Divorce", "MCR 3.206", None, None),
    ("SUMMONS", True, "Summons (SCAO Form MC 01)", "MCR 2.102", None, None),
    ("VERIFIED_STMT", True, "Verified Statement (SCAO Form FOC 23)", "MCR 3.206(B)", None, None),
    ("UCCJEA", True, "UCCJEA Affidavit (SCAO Form MC 416)", "MCL 722.1209", None, None),
    ("PROOF_SERVICE", False, "Proof of Service", "MCR 2.104", None, None),
    ("FRIEND_OF_CT", False, "Friend of Court Recommendation", "MCL 552.505", None, None),
    ("EXHIBIT", False, "Exhibits", None, None, None),
]

PPO_FILING_REQUIREMENTS = [
    ("PPO_PETITION", True, "Petition for PPO (SCAO Form CC 375)", "MCL 600.2950", None, None),
    ("PPO_INFO", True, "PPO Information Sheet", "MCL 600.2950(3)", None, None),
    ("EXHIBIT", False, "Supporting Evidence", None, None, None),
]

CRIMINAL_FILING_REQUIREMENTS = [
    ("INFORMATION", True, "Information / Complaint", "MCR 6.112", None, None),
    ("WARRANT", True, "Arrest Warrant or Summons", "MCR 6.102", None, None),
    ("PROOF_SERVICE", False, "Proof of Service", "MCR 6.103", None, None),
]

PROBATE_ESTATE_REQUIREMENTS = [
    ("PETITION", True, "Petition for Probate (SCAO Form PC 558)", "MCL 700.3301", None, None),
    ("DEATH_CERT", True, "Certified Death Certificate", "MCL 700.3301(1)(a)", None, None),
    ("WILL_ORIG", False, "Original Will (if testate)", "MCL 700.3402", None, None),
    ("TESTIMONY", True, "Testimony to Identify Heirs (SCAO Form PC 565)", "MCL 700.3301", None, None),
    ("NOTICE_HEARING", True, "Notice of Hearing", "MCR 5.105", None, None),
    ("RENUNC", False, "Renunciation / Nomination of PR", "MCL 700.3303", None, None),
    ("BOND", False, "Bond (if required)", "MCL 700.3603", None, None),
]

PROBATE_GUARDIANSHIP_REQUIREMENTS = [
    ("PETITION", True, "Petition for Guardianship (SCAO Form PC 660)", "MCL 700.5303", None, None),
    ("PHYSICIAN_RPT", True, "Physician Report (SCAO Form PC 625)", "MCL 700.5303(3)", None, None),
    ("PROOF_SERVICE", True, "Proof of Service on Ward", "MCR 5.105", None, None),
    ("NOTICE_HEARING", True, "Notice of Hearing", "MCR 5.105", None, None),
    ("BACKGROUND", False, "Background Check / ICHAT", None, None, None),
]

APPEALS_FILING_REQUIREMENTS = [
    ("CLAIM_APPEAL", True, "Claim of Appeal", "MCR 7.204(A)", None, None),
    ("ENTRY_ORDER", True, "Entry of Order Being Appealed", "MCR 7.204(A)(2)", None, None),
    ("TRANSCRIPT_ORDER", True, "Transcript Order Form", "MCR 7.210", None, None),
    ("DOCKETING_STMT", True, "Docketing Statement", "MCR 7.204(B)", None, None),
    ("PROOF_SERVICE", True, "Proof of Service", "MCR 7.204(A)(3)", None, None),
    ("APP_BRIEF", False, "Appellant's Brief", "MCR 7.212", 50, "Due within 56 days"),
]

SUPREME_COURT_REQUIREMENTS = [
    ("APP_LEAVE", True, "Application for Leave to Appeal", "MCR 7.305(B)", None, None),
    ("DECISION_BELOW", True, "Decision of Court of Appeals", "MCR 7.305(B)(1)", None, None),
    ("PROOF_SERVICE", True, "Proof of Service", "MCR 7.305(B)(6)", None, None),
    ("APP_BRIEF", False, "Supporting Brief", "MCR 7.305(B)(5)", 50, None),
    ("APPENDIX", False, "Appendix", "MCR 7.305(B)(4)", None, None),
]

FAMILY_MOTION_REQUIREMENTS = [
    ("MOT_MODIFY", True, "Motion to Modify Custody/Support/Parenting Time", "MCR 3.207 / MCL 722.27", None, None),
    ("MOT_CONTEMPT", True, "Motion for Contempt / Show Cause", "MCR 3.207", None, "Requires affidavit of facts"),
    ("MOT_RELOCATION", True, "Motion re: Change of Domicile/Relocation", "MCL 722.31", None, None),
]

PROBATE_MOTION_REQUIREMENTS = [
    ("MOT_REMOVE_PR", True, "Motion to Remove Personal Representative", "MCL 700.3611", None, None),
    ("MOT_APPROVE_ACCT", True, "Motion to Approve Account / Settlement", "MCL 700.3703", None, None),
]


def seed_database(reset: bool = False, url: str | None = None) -> None:
    url = url or settings.database_url
    document_service.ensure_bucket()
    if make_url(url).get_dialect().is_async:
        asyncio.run(_seed_with_async_driver(url, reset))
        return
    engine = create_engine(url, echo=False)
    try:
        with engine.connect() as connection:
            _prepare_schema(connection, reset)
        _populate(engine)
    finally:
        engine.dispose()


async def _seed_with_async_driver(url: str, reset: bool) -> None:
    engine = create_async_engine(url, echo=False)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_prepare_schema, reset)
            await connection.run_sync(_populate)
            await connection.commit()
    finally:
        await engine.dispose()


def _prepare_schema(connection: Connection, reset: bool) -> None:
    if reset:
        print("Reset: dropping application tables...")
        Base.metadata.drop_all(connection)
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("DROP TYPE IF EXISTS deliverystatus")
        connection.commit()
    if connection.dialect.name == "sqlite":
        prepare_demo_connection(connection)
    else:
        command.upgrade(alembic_config(connection), "head")
    connection.commit()


def _populate(bind: Engine | Connection) -> None:
    with Session(bind) as session:
        existing = session.query(Court).first()
        if existing:
            print("Database already seeded. Skipping.")
            return

        print("Seeding Michigan courts...")

        users = [
            User(
                email="attorney@demo.muefs.gov",
                first_name="Jane",
                last_name="Doe",
                user_type=UserType.ATTORNEY,
                bar_number="P12345",
                bar_number_verified=True,
                firm_name="Doe & Associates PLLC",
                phone="313-555-0100",
            ),
            User(
                email="clerk@demo.muefs.gov",
                first_name="Dana",
                last_name="Whitfield",
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
            User(
                email="srl@demo.muefs.gov",
                first_name="Maria",
                last_name="Williams",
                user_type=UserType.SELF_REPRESENTED,
                phone="248-555-0400",
            ),
            User(
                email="public@demo.muefs.gov",
                first_name="Alex",
                last_name="Rivera",
                user_type=UserType.PUBLIC,
                phone="313-555-0500",
            ),
        ]
        session.add_all(users)
        session.flush()
        print(f"  Created {len(users)} demo users")

        court_count = 0

        for circuit_num, counties, city in CIRCUIT_COURTS:
            county = counties[0]
            name = f"{_ordinal(circuit_num)} Circuit Court"
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

            all_types = (
                CIRCUIT_CIVIL_CASE_TYPES
                + FAMILY_CASE_TYPES
                + CRIMINAL_CASE_TYPES
            )
            for code, type_name, category, fee in all_types:
                ct = CaseType(
                    court_id=court.id,
                    code=code,
                    name=type_name,
                    category=category,
                    filing_fee_cents=fee,
                )
                session.add(ct)

            session.flush()

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

                session.add(FilingChecklist(
                    court_id=court.id,
                    case_type_id=civil_ct.id,
                    motion_type="Summary Disposition (MCR 2.116)",
                    checklist_items={
                        "items": [
                            {"label": "Motion for Summary Disposition", "required": True},
                            {"label": "Brief in Support of Motion", "required": True},
                            {"label": "Statement of Material Facts", "required": False},
                            {"label": "Proposed Order", "required": False},
                            {"label": "Proof of Service", "required": True},
                            {"label": "Supporting Affidavits", "required": False},
                            {"label": "Exhibits", "required": False},
                        ]
                    },
                    help_text=(
                        "Filed under MCR 2.116. Brief limited"
                        " to 20 pages. Response due 21 days"
                        " after service."
                    ),
                    mcr_url=(
                        "https://courts.michigan.gov/courts/michigansupremecourt/rules/court-rules-702/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2116-summary-disposition"
                    ),
                ))

            fam_ct = session.query(CaseType).filter_by(
                court_id=court.id, code="FAM-DIV"
            ).first()
            if fam_ct:
                for doc_code, required, desc, mcr, page_limit, notes in FAMILY_FILING_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=fam_ct.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))
                for doc_code, required, desc, mcr, page_limit, notes in FAMILY_MOTION_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=fam_ct.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))

            ppo_ct = session.query(CaseType).filter_by(
                court_id=court.id, code="FAM-PPO"
            ).first()
            if ppo_ct:
                for doc_code, required, desc, mcr, page_limit, notes in PPO_FILING_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=ppo_ct.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))

            crim_ct = session.query(CaseType).filter_by(
                court_id=court.id, code="CR-FEL"
            ).first()
            if crim_ct:
                for (doc_code, required, desc,
                     mcr, page_limit, notes) in CRIMINAL_FILING_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=crim_ct.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))

            if civil_ct:
                for doc_code, required, desc, mcr, page_limit, notes in MOTION_FILING_REQUIREMENTS:
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
                session.add(FilingChecklist(
                    court_id=court.id,
                    case_type_id=civil_ct.id,
                    motion_type="General Motion (MCR 2.119)",
                    checklist_items={
                        "items": [
                            {"label": "Motion", "required": True},
                            {"label": "Brief in Support", "required": False},
                            {"label": "Proposed Order", "required": False},
                            {"label": "Notice of Hearing (9 days before)", "required": True},
                            {"label": "Proof of Service", "required": True},
                            {"label": "Supporting Affidavits", "required": False},
                        ]
                    },
                    help_text=(
                        "MCR 2.119 governs all motion practice. A brief"
                        " is required only when the motion presents an"
                        " issue of law (MCR 2.119(A)(2)) and may be"
                        " combined with the motion; a proposed order is"
                        " best practice (entry under MCR 2.602). Brief"
                        " limited to 20 pages; notice of hearing served"
                        " at least 9 days before the hearing date."
                    ),
                    mcr_url=(
                        "https://courts.michigan.gov/courts/"
                        "michigansupremecourt/rules/court-rules-702/"
                        "chapter-2-civil-procedure/subchapter-2100"
                        "-pleadings-and-motions/rule-2119-motion-practice"
                    ),
                ))

                session.add(FilingChecklist(
                    court_id=court.id,
                    case_type_id=civil_ct.id,
                    motion_type="Discovery Motion (MCR 2.313)",
                    checklist_items={
                        "items": [
                            {"label": "Motion to Compel / Protective Order", "required": True},
                            {"label": "Brief in Support", "required": True},
                            {"label": "Meet-and-Confer Certification", "required": False},
                            {"label": "Proposed Order", "required": False},
                            {"label": "Proof of Service", "required": True},
                            {"label": "Copy of Discovery Request at Issue", "required": False},
                        ]
                    },
                    help_text=(
                        "Under MCR 2.313(A)(5), a good-faith effort to"
                        " resolve the dispute is a factor in awarding"
                        " motion expenses, so a meet-and-confer"
                        " certification is recommended best practice,"
                        " not a required filing. A motion to compel a"
                        " non-party subpoena must include the subpoena"
                        " and proof of service (MCR 2.313(A)(2)(c))."
                    ),
                    mcr_url=(
                        "https://courts.michigan.gov/courts/"
                        "michigansupremecourt/rules/court-rules-702/"
                        "chapter-2-civil-procedure/subchapter-2300"
                        "-discovery/rule-2313-failure-to-provide"
                        "-discovery-sanctions"
                    ),
                ))

                session.add(FilingChecklist(
                    court_id=court.id,
                    case_type_id=civil_ct.id,
                    motion_type="Default Judgment (MCR 2.603)",
                    checklist_items={
                        "items": [
                            {"label": "Request / Motion for Default", "required": True},
                            {"label": "Affidavit of Non-Military Service", "required": True},
                            {"label": "Proof of Service of Process", "required": True},
                            {"label": "Proposed Default Judgment", "required": True},
                            {"label": "Affidavit of Damages (if unliquidated)", "required": False},
                        ]
                    },
                    help_text=(
                        "MCR 2.603. Default may be entered if"
                        " defendant fails to plead or defend"
                        " within 21 days of service. Must verify"
                        " non-military status under SCRA."
                    ),
                    mcr_url=(
                        "https://courts.michigan.gov/courts/"
                        "michigansupremecourt/rules/court-rules-702/"
                        "chapter-2-civil-procedure/subchapter-2600"
                        "-judgment/rule-2603-default-default-judgment"
                    ),
                ))

                session.add(FilingChecklist(
                    court_id=court.id,
                    case_type_id=civil_ct.id,
                    motion_type="Motion for Reconsideration (MCR 2.119(F))",
                    checklist_items={
                        "items": [
                            {"label": "Motion for Reconsideration", "required": True},
                            {"label": "Brief in Support (often short)", "required": True},
                            {"label": "Proposed Order", "required": True},
                            {"label": "Proof of Service", "required": True},
                        ]
                    },
                    help_text="MCR 2.119(F). Usually decided without oral argument. Timely filing critical.",
                    mcr_url="https://courts.michigan.gov/courts/michigansupremecourt/rules/court-rules-702/chapter-2-civil-procedure/subchapter-2100-pleadings-and-motions/rule-2119-motion-practice",
                ))

                session.add(FilingChecklist(
                    court_id=court.id,
                    case_type_id=civil_ct.id,
                    motion_type="Motion in Limine (MRE 103)",
                    checklist_items={
                        "items": [
                            {"label": "Motion in Limine", "required": True},
                            {"label": "Brief in Support", "required": True},
                            {"label": "Proposed Order", "required": True},
                            {"label": "Proof of Service", "required": True},
                        ]
                    },
                    help_text="Evidentiary motion to exclude or limit evidence at trial. Often filed pre-trial.",
                    mcr_url="",
                ))

                session.add(FilingChecklist(
                    court_id=court.id,
                    case_type_id=civil_ct.id,
                    motion_type="Motion for Preliminary Injunction / TRO (MCR 3.310)",
                    checklist_items={
                        "items": [
                            {"label": "Motion for TRO or Preliminary Injunction", "required": True},
                            {"label": "Brief with irreparable harm showing", "required": True},
                            {"label": "Affidavits / Evidence", "required": True},
                            {"label": "Proposed Order (with findings)", "required": True},
                            {"label": "Proof of Service (or ex parte justification)", "required": True},
                            {"label": "Bond / Security (often required)", "required": False},
                        ]
                    },
                    help_text="MCR 3.310. TRO may be ex parte for 14 days; PI requires hearing. Specific findings required.",
                    mcr_url="https://courts.michigan.gov/courts/michigansupremecourt/rules/court-rules-702/chapter-3-special-proceedings-and-actions/subchapter-3300-provisional-and-final-remedies-and-special-proceedings/rule-3310-injunctions",
                ))

            subp_ct = session.query(CaseType).filter_by(
                court_id=court.id, code="CIV-SUBP"
            ).first()
            if subp_ct:
                for (doc_code, required, desc,
                     mcr, page_limit, notes) in SUBPOENA_FILING_REQUIREMENTS:
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

            session.flush()

            dc_civil = session.query(CaseType).filter_by(
                court_id=court.id, code="CIV-GEN"
            ).first()
            if dc_civil:
                for doc_code, required, desc, mcr, page_limit, notes in DISTRICT_CIVIL_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=dc_civil.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))

            dc_sm = session.query(CaseType).filter_by(
                court_id=court.id, code="SM-CLM"
            ).first()
            if dc_sm:
                for doc_code, required, desc, mcr, page_limit, notes in SMALL_CLAIMS_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=dc_sm.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))

            dc_crim = session.query(CaseType).filter_by(
                court_id=court.id, code="CR-MISD"
            ).first()
            if dc_crim:
                for (doc_code, required, desc,
                     mcr, page_limit, notes) in CRIMINAL_FILING_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=dc_crim.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))

            dc_count += 1

        print(f"  Created {dc_count} district courts")

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

            session.flush()

            pc_estate = session.query(CaseType).filter_by(
                court_id=court.id, code="PR-EST"
            ).first()
            if pc_estate:
                for doc_code, required, desc, mcr, page_limit, notes in PROBATE_ESTATE_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=pc_estate.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))
                for doc_code, required, desc, mcr, page_limit, notes in PROBATE_MOTION_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=pc_estate.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))

            pc_guard = session.query(CaseType).filter_by(
                court_id=court.id, code="PR-GRDN"
            ).first()
            if pc_guard:
                for (doc_code, required, desc,
                     mcr, page_limit, notes) in PROBATE_GUARDIANSHIP_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=pc_guard.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))

            pc_count += 1

        print(f"  Created {pc_count} probate courts")

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

            session.flush()

            app_civil = session.query(CaseType).filter_by(
                court_id=court.id, code="APP-CIV"
            ).first()
            if app_civil:
                for doc_code, required, desc, mcr, page_limit, notes in APPEALS_FILING_REQUIREMENTS:
                    session.add(FilingRequirement(
                        court_id=court.id,
                        case_type_id=app_civil.id,
                        document_type_code=doc_code,
                        is_required=required,
                        description=desc,
                        mcr_reference=mcr,
                        page_limit=page_limit,
                        format_notes=notes,
                    ))

        print("  Created 4 Court of Appeals districts")

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
                filing_fee_cents=fee,
            ))

        session.flush()

        sc_civil = session.query(CaseType).filter_by(
            court_id=court.id, code="APP-CIV"
        ).first()
        if sc_civil:
            for doc_code, required, desc, mcr, page_limit, notes in SUPREME_COURT_REQUIREMENTS:
                session.add(FilingRequirement(
                    court_id=court.id,
                    case_type_id=sc_civil.id,
                    document_type_code=doc_code,
                    is_required=required,
                    description=desc,
                    mcr_reference=mcr,
                    page_limit=page_limit,
                    format_notes=notes,
                ))

        print("  Created Michigan Supreme Court")

        third_circuit = session.query(Court).filter(
            Court.name == "3rd Circuit Court"
        ).first()
        if third_circuit:
            session.add(UserCourtRole(
                user_id=users[1].id,
                court_id=third_circuit.id,
                role=CourtRole.CLERK,
            ))
            session.flush()
            print(f"  Assigned clerk to {third_circuit.name} (court_id={third_circuit.id})")

        from app.models.case import Case, CaseParticipant, CaseStatus, ParticipantRole
        from app.models.filing import FilingEnvelope, FilingStatus
        from app.models.user import FavoriteCase, FavoriteCourt

        now = datetime.now(UTC)
        attorney = users[0]
        clerk_user = users[1]
        srl_user = users[3]

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
            wayne_divorce = session.query(CaseType).filter_by(
                court_id=wayne_circuit.id, code="FAM-DIV"
            ).first()
            wayne_subp = session.query(CaseType).filter_by(
                court_id=wayne_circuit.id, code="CIV-SUBP"
            ).first()
            assert wayne_civil is not None

            case1 = Case(
                court_id=wayne_circuit.id,
                case_number=f"{now.year:04d}-000001-CZ",
                case_type_id=wayne_civil.id,
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
                access_enabled=True, reviewed_at=now,
            ))

            filing1 = FilingEnvelope(
                court_id=wayne_circuit.id, case_id=case1.id,
                case_type_id=wayne_civil.id,
                filer_id=attorney.id,
                case_title="Johnson v. Smith Industries LLC",
                filing_description=(
                    "Initial complaint for breach of contract"
                    " - failure to deliver goods per"
                    " Purchase Order #2024-8891"
                ),
                status=FilingStatus.ACCEPTED,
                submitted_at=now, reviewed_at=now, reviewer_id=clerk_user.id,
            )
            session.add(filing1)
            session.flush()
            session.add(sample_document(
                filing1, "COMPLAINT", "Complaint for Breach of Contract",
            ))

            filing1_motion = FilingEnvelope(
                court_id=wayne_circuit.id, case_id=case1.id,
                case_type_id=wayne_civil.id,
                filer_id=attorney.id,
                case_title="Johnson v. Smith Industries LLC",
                filing_description=(
                    "Motion for Summary Disposition under"
                    " MCR 2.116(C)(10) - No genuine issue"
                    " of material fact"
                ),
                status=FilingStatus.SUBMITTED,
                submitted_at=now,
            )
            session.add(filing1_motion)
            session.flush()
            session.add(sample_document(
                filing1_motion, "MOTION", "Motion for Summary Disposition",
            ))
            session.add(sample_document(
                filing1_motion, "BRIEF", "Brief in Support of Motion for Summary Disposition",
            ))

            case2 = Case(
                court_id=wayne_circuit.id,
                case_number=f"{now.year:04d}-000002-NO",
                case_type_id=wayne_tort.id if wayne_tort else wayne_civil.id,
                title="Williams v. City of Detroit",
                status=CaseStatus.OPEN,
                filed_date=now,
            )
            session.add(case2)
            session.flush()

            session.add(CaseParticipant(
                case_id=case2.id,
                user_id=srl_user.id,
                role=ParticipantRole.PLAINTIFF,
                party_name="Maria Williams",
                access_enabled=True, reviewed_at=now,
            ))
            session.add(CaseParticipant(
                case_id=case2.id, role=ParticipantRole.DEFENDANT,
                party_name="City of Detroit",
            ))
            session.add(CaseParticipant(
                case_id=case2.id, user_id=attorney.id,
                role=ParticipantRole.ATTORNEY_PLAINTIFF,
                party_name="Jane Doe", attorney_bar_number="P12345",
                access_enabled=True, reviewed_at=now,
            ))

            filing2 = FilingEnvelope(
                court_id=wayne_circuit.id, case_id=case2.id,
                case_type_id=wayne_tort.id if wayne_tort else wayne_civil.id,
                filer_id=attorney.id,
                case_title="Williams v. City of Detroit",
                filing_description=(
                    "Complaint for personal injury"
                    " - sidewalk defect on Michigan Ave"
                ),
                status=FilingStatus.ACCEPTED,
                submitted_at=now, reviewed_at=now, reviewer_id=clerk_user.id,
            )
            session.add(filing2)
            session.flush()
            session.add(sample_document(
                filing2, "COMPLAINT", "Complaint for Personal Injury",
            ))

            if wayne_divorce:
                case3 = Case(
                    court_id=wayne_circuit.id,
                    case_number=f"{now.year:04d}-000003-DM",
                    case_type_id=wayne_divorce.id,
                    title="Thompson v. Thompson",
                    is_sealed=True,
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
                    filing_description="Complaint for Divorce with Minor Children",
                    status=FilingStatus.ACCEPTED,
                    submitted_at=now, reviewed_at=now, reviewer_id=clerk_user.id,
                )
                session.add(filing3)
                session.flush()
                session.add(sample_document(
                    filing3, "COMPLAINT", "Complaint for Divorce",
                ))

            if wayne_subp:
                case4 = Case(
                    court_id=wayne_circuit.id,
                    case_number=f"{now.year:04d}-000004-PZ",
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
                    filing_description=(
                        "Domesticating out-of-state subpoena"
                        " per the Uniform Interstate Depositions"
                        " and Discovery Act (MCL 600.2201 et seq.)"
                    ),
                    status=FilingStatus.SUBMITTED,
                    submitted_at=now,
                )
                session.add(filing4)
                session.flush()
                session.add(sample_document(
                    filing4, "SUBPOENA", "Ohio Subpoena - Authenticated Copy",
                ))
                session.add(sample_document(
                    filing4, "PROPOSED_SUBP", "Proposed Michigan Subpoena",
                ))

            filing5 = FilingEnvelope(
                court_id=wayne_circuit.id,
                case_type_id=wayne_civil.id,
                filing_type="initial",
                filer_id=attorney.id,
                case_title="Anderson v. Metro Health Systems",
                filing_description="Complaint for medical malpractice",
                status=FilingStatus.RETURNED,
                submitted_at=now, reviewed_at=now, reviewer_id=clerk_user.id,
                rejection_reason=(
                    "Missing Affidavit of Merit required by"
                    " MCL 600.2912d for medical malpractice"
                    " cases. Please attach and resubmit."
                ),
            )
            session.add(filing5)
            session.flush()
            session.add(sample_document(
                filing5, "COMPLAINT", "Complaint for Medical Malpractice",
            ))

            session.add(FavoriteCase(
                user_id=attorney.id, case_id=case1.id,
                notes="Key breach of contract case - motion for SD pending",
            ))

            if wayne_circuit:
                session.add(FavoriteCourt(
                    user_id=attorney.id, court_id=wayne_circuit.id,
                    notes="Primary court - Wayne County",
                ))
            oakland_court = session.query(Court).filter_by(name="6th Circuit Court", county="Oakland").first()
            if oakland_court:
                session.add(FavoriteCourt(
                    user_id=attorney.id, court_id=oakland_court.id,
                    notes="Oakland County filings",
                ))

            demo_cases = session.query(Case).count()
            demo_filings = session.query(FilingEnvelope).count()
            print(f"  Created {demo_cases} demo cases with {demo_filings} filings")

        dupes = (
            session.query(
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
        if dupes:
            raise ValueError(
                f"{len(dupes)} duplicate filing-requirement rows seeded; first: {dupes[:5]}"
            )

        session.commit()

        total = session.query(Court).count()
        total_types = session.query(CaseType).count()
        total_reqs = session.query(FilingRequirement).count()
        print(
            f"\nSeed complete: {total} courts,"
            f" {total_types} case types,"
            f" {total_reqs} filing requirements"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed Michigan court demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate the application tables before seeding "
        "(Keycloak tables and stored documents are untouched).",
    )
    seed_database(reset=parser.parse_args().reset)
