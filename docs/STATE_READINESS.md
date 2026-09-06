# State implementation evaluation

MUEFS remains a proof of concept. The objective is an efiling suite that can withstand a
state's implementation evaluation, including actual filing operations, integrations,
security, accessibility, and recovery. Passing a demo or this repository's tests does not
establish state approval or production readiness.

## Operating requirements and current evidence

| Requirement | Current evidence | Remaining work |
|---|---|---|
| Prove what was submitted | Each new submission has a retained transaction ID, UTC receipt time, filer name, document manifest and SHA-256 fingerprints, payment reference where present, and a downloadable receipt. A read-only recovery audit compares stored bytes and retained transaction references. | Court-approved retention schedules, trusted time monitoring, external archival controls and validation of the deployed storage/recovery configuration. |
| Preserve corrections and decisions | Corrections create another numbered submission. Earlier document bytes remain downloadable by the filer and court staff. Acceptance, return, rejection, CMS failure and signed filing-date orders are separate retained events. | Court procedures for deciding relief, certified/file-stamped copies and court-approved retention. |
| Survive retries and simultaneous actions | Optional UUID `Idempotency-Key` on submission prevents duplicate receipts. PostgreSQL row locks refresh previously read state. Batch review uses a savepoint per filing. | Operational load tests, outages during real downstream submission, and end-to-end reconciliation. |
| Publish reviewed public copies | Assigned staff prepare and inspect a separate PDF and public title, explicitly publish it, and withdraw public access with retained authority/history. Originals and receipts stay intact; fee-waiver records cannot use this publication path. | Court-approved classification/redaction policy, approved review tools, storage immutability and retention schedules. |
| Protect private material | Private envelopes and receipts require filer or court-staff access. Dockets exclude waiver application data, confidential document metadata, superseded documents and other filers' drafts. Fee-waiver documents are nonpublic even if the filer omits the checkbox. | Full classification/retention policy for every case and document type; independent security assessment. |
| Control case participation and access | Assigned staff record participants, counsel representation and explicit restricted-case grants with retained reasons, before/after history, stale-edit checks and revocation. Filing acceptance no longer assigns party roles or grants case access. | Court-approved access rules, review of legacy records, CMS appearance/withdrawal synchronization, limited-scope representation and service enrollment. |
| Record the correct legal filing date | Receipt instants and filing dates are separate. Published calendars establish business dates. Assigned staff can record a signed order establishing a different date, with retained before/after evidence and explicit case opening date changes. Acceptance honors the order without rewriting the receipt. | Court verification of calendars and signed orders, motion/adjudication procedures, downstream CMS synchronization and review of closures published after acceptance. Correcting a document does not automatically preserve its legal filing date. |
| Resolve fee waivers correctly | A completed application accompanies the filing. Clerk waivers, referral and judicial decisions are separate court-scoped actions. Signed decision PDFs and denial amounts remain in private history; a filer can pay after denial without resubmitting. | Actual notice delivery, de novo review and judicial assignment, deadline calculation, case-wide continuation and reinstatement, court verification of signed forms and prisoner-specific procedures. |
| Establish fees and account for payments | Assigned court staff record itemized assessments with authority, reasons and retained documents. Balances use completed payments allocated to that filing; revised assessments preserve earlier credits and expose overpayments. | Court validation of assessments and fee schedules, a real hosted payment processor, signed webhooks, reconciliation, refunds and accounting exports. |
| Deliver electronic service | Service-only documents can be recorded. | Verified service contacts, consent/eligibility, real transmission, failures/retries, non-electronic alternatives and retained proof. A recorded document or in-app notice is not proof of service. |
| Send filing alerts reliably | An opt-in SMTP outbox commits with filing changes, checks verified recipients, retains messages and attempts, retries temporary failures and exposes uncertain outcomes to assigned court staff. | A court-approved relay and sender domain, bounce/delivery feedback, operational alerting and court approval of legally sufficient notice content and procedures. Generic email alerts do not establish legal service. |
| Connect to the court's system of record | Acceptance is explicitly blocked outside demo mode when CMS integration is absent. | A documented court/vendor contract, credentialed sandbox, document/code mapping, idempotent delivery, status callbacks, error recovery and reconciliation. |
| Operate statewide | Explicit identity provisioning, delegated court administration, immediate checks on subsequent requests after revocation, retained changes, PostgreSQL migrations and deployment guidance exist. | State federation and lifecycle integration, access recertification, availability targets, incident response, backup restoration drills, disaster recovery and migration from incumbent systems. |
| Serve the whole public | Responsive filing and history pages, keyboard controls and guided filing exist. | Independent accessibility testing, assistive-technology testing, language access, paper-filing accommodations and usability evaluation with self-represented filers. |

## Implemented receipt workflow

1. The filer submits an envelope. The application commits its status, receipt and in-app
   notice together. The receipt preserves the submitted document metadata and payment
   reference rather than reading those fields from the subsequently edited envelope.
2. The filer opens **Receipts & history** from My Filings, the submission confirmation or
   a notification. Court staff can open the same history from the review queue.
3. A returned filing can be corrected. Removing a previously submitted document removes
   it from the next attempt, while keeping its stored bytes and original receipt private.
4. Resubmission creates another numbered receipt. A clerk decision is recorded separately.
   CMS failure is retained as a failed attempt and does not become an acceptance.
5. Receipt history is paginated. Each transaction can be downloaded as JSON; the displayed
   page can be printed. Downloads use the authenticated client, including for retained files.

`GET /api/v1/filings/{id}/history` is private to the filer and authorized staff. It is not
a public record-verification API. `GET /api/v1/filings/{id}` is likewise a private envelope;
case viewers use the smaller docket response at `/api/v1/cases/{id}/filings`.

The client retains a submission idempotency key while retrying a failed request. Reusing
that key returns the current envelope without making a new submission. A correction must
use a new key. Clients must inspect the returned status; replaying an old key does not
submit changes made since its original use.

## Verification and deployment

Behavioral coverage lives in:

- `backend/tests/test_filing_history.py`: receipts, corrections, private access, historical
  downloads, stable paging, SQL retention guards and rollback of a failed batch item.
- `backend/tests/test_filing_concurrency.py`: simultaneous reviews and submission retries
  on PostgreSQL, plus retention guards on both model-created and Alembic-migrated schemas.
- `backend/tests/test_filing_migration.py`: upgrades preserve legacy filings and documents
  without fabricating old receipts. Repeated startup does not duplicate the migration.

Run `pytest tests/` from `backend`. Set `MUEFS_TEST_POSTGRES_URL` to a disposable PostgreSQL
database to include concurrency checks; each test creates and removes its own schema. CI
provides PostgreSQL 16 for these tests.

Production deployment requires `alembic upgrade head` before the application starts.
Migration `e91c62d7a104` adds retained transactions and archival document fields. It refuses
an automatic downgrade that would erase filing evidence. Take a verified backup first and
use the court's recovery procedure for rollback. Existing demo SQLite databases use the
same migration on startup. No receipt is invented for a filing submitted before tracking.

Database triggers block transaction UPDATE and DELETE in SQLite and PostgreSQL. Database
owners can remove these controls; they are not a substitute for restricted production
roles, protected backups or an external archive. Document retention needs a court-approved
policy before production use. Email alerts require an explicitly configured relay and worker;
the portal retains notices even when delivery is disabled or fails.

## Independent fee waiver review

The payment screen links to SCAO's approved MC 20 and accepts an uploaded application.
The required free-text hardship question has been removed. A pending request must have
an application attachment before submission; the system does not verify the form's
contents or signature. The application and signed decision PDFs are nonpublic.

Court staff can select **Pending Fee Waivers** in the review queue, including waivers on
filings that were already accepted. The private history page exposes only actions allowed
by the viewer's assignment to that court:

- Clerks can record a signed waiver for qualifying public assistance or qualifying legal
  services representation, or refer the request for judicial review.
- Judges can record a signed grant or denial. Denial requires the reason in the order and
  the amount due. Administrative access alone does not authorize these decisions, and a
  judge cannot decide their own application.
- Filing acceptance, return and rejection do not change waiver decisions. A decided or
  referred request cannot be reset by editing the returned filing.

`POST /api/v1/clerk/filings/{id}/fee-waiver` commits the filing state, PDF metadata and private
history event in the same database transaction. The stored PDF stays outside the filer's editable
attachment list. Competing decisions use the envelope row lock; only one decision wins.
The existing private history response includes the waiver state and allowed actions.

After denial, the filer can record a simulated payment of the remaining balance from
history in demo mode. The server uses the amount in the decision, less completed payments
allocated to this filing, including on a corrected filing. Payment creates its own receipt and does not change
the submission time, number of submissions, filing status or denial. It does not establish
the legal filing date. Real payment processing remains unconfigured.

Court staff must still send the signed decision and required notice through an authorized
channel. The in-app notice does not establish delivery, start a calculated deadline, issue
a stay, or arrange de novo review. The application does not automatically reject a filing
for missed payment. These procedures, case-wide waiver continuation/reinstatement, refunds
and prisoner-specific requirements remain implementation work.

Migration `f38d104ac927` adds referral/decision times, the amount due and an index for the
pending-waiver queue. Existing waiver booleans are preserved and shown as legacy state
when no independent decision time exists. No signed order is fabricated from an earlier
acceptance. The migration refuses a downgrade that would discard decision state.

`backend/tests/test_fee_waivers.py` covers application requirements, court-role boundaries,
private signed orders, retained downloads, denial/payment and draft-edit bypass attempts.
The PostgreSQL suite also races waiver decisions and post-denial payments. The upload
pipeline is shared with filer documents so size limits, MIME inspection, malware screening
and off-thread PDF processing apply to both.

## Court fee assessments and payment balances

Fee determination requires more context than a court, case type and the word "subsequent."
The official Michigan [circuit fee table](https://www.courts.michigan.gov/siteassets/court-administration/resources/cfee.pdf)
and [district fee table](https://www.courts.michigan.gov/siteassets/court-administration/resources/dfee.pdf)
distinguish charges and exceptions. The application no longer treats every subsequent
filing as a motion, infers charges from fee labels, sums overlapping schedule rows, or
adds a guessed electronic filing charge.

The filer can request fee review from the fee screen. This retains the current document
manifest and reason, and places the request in the court's **Fee Reviews** queue. It does
not submit a draft, establish its filing date, or accept a filing. An assigned court clerk,
judge or court administrator can inspect the private originals and record an itemized
assessment with an authority reference, reason and explicit review confirmation. They
cannot assess their own filing or override an independent fee-waiver decision. A zero-dollar
assessment requires an item explaining the absence of a charge. Court procedures must
establish the reviewer's authority and verify the referenced schedule and exceptions.

Each assessment is an append-only filing transaction with the reviewed document manifest.
Changing draft attachments invalidates it. A replacement assessment retains the old record
and uses a new version. A short shared envelope lock lets the fee screen read the documents,
assessment and balance consistently in one response; mutations lock the same envelope.
Stale assessment and payment requests fail with HTTP 409, including an old payment form
whose displayed amount happens to match the new assessment.

Payments are explicitly allocated to an envelope and preserve their assessment basis.
The balance credits positive, completed payments from that filer; failed, refunded,
unallocated and other payers' records cannot clear the obligation. Higher reassessments
require only the remaining balance. Lower reassessments expose the overpayment without
inventing a refund. Submission receipts retain the assessment and all allocated payment
records as they existed at submission. Signed waiver decisions remain the basis for waiver
amounts, and a pending application can accompany a submission for court review.

Demo initial-filing amounts are visibly synthetic examples. Outside demo mode, seeded
amounts and simulated credits cannot satisfy fee requirements: an assessment, applicable
waiver state or service-only filing is required. Real payment processing remains unavailable;
the application does not collect card/bank data or claim to move money.

`GET /api/v1/filings/{id}/fees` replaces `POST /api/v1/payments/calculate`. It returns the
current fee state and the matching private filing context. Filers request review through
`POST /api/v1/filings/{id}/fee-review`; assigned staff use `GET /api/v1/clerk/fee-reviews`
and `POST /api/v1/clerk/filings/{id}/fees`. Both review mutations require `expected_version`.
`POST /api/v1/payments/process` requires `expected_fee_version` and the exact remaining balance.

Migration `c3d9f06a21b8` preserves only unambiguous historical payment allocations with a
matching payer and marks legacy payments as simulated. It does not fabricate assessment
records or allocation evidence. Ambiguous historical payments require reconciliation.
The migration refuses destructive downgrade. `test_fee_assessments.py` covers the actual
request, assessment, correction, payment and submission workflow; the PostgreSQL suite
also tests duplicate requests, simultaneous document edits, consistent reads and rollback.

## Court calendars and filing dates

The calendar page at `/courts/{court_id}/calendar` is public. A user with an administrator
or judge assignment to that court can publish a revision; clerks have read-only access.
Each revision records an IANA timezone, inclusive date coverage, dated closure reasons,
approving authority or source, publisher and UTC publication time. Publication also creates
an audit entry. A court must verify the entries; the application does not supply or certify
a holiday list. All unlisted weekdays within the published coverage are treated as open.

The implementation applies MCR 1.109(G)(5)(b)'s receipt-day/business-day rule. It calculates
the local receipt date and advances over weekends and listed closures, using the newest
revision covering each date. Adjacent calendars can cover a year-end transition. Missing
coverage or a timezone change before the next business day produces an unresolved date.
The calculation loads the relevant revisions in one query, with no database query per day.

Submission preserves the UTC receipt instant and calendar assessment, including revision
IDs and skipped dates. Unless a court order has established the date for that submission,
acceptance reassesses the same receipt instant against the published calendar and records
a separate event if the assessment changed. New cases keep the receipt
instant in `filed_date` and the civil date in `filing_date`; neither uses the clerk's acceptance
time. Date-only fields display consistently across viewer timezones. Search and docket
detail share the same public response schema, and timestamp responses include a UTC offset.

If coverage is unresolved, submission still records receipt. Production acceptance returns
409 until the court resolves the calendar or records a signed filing-date order; demo acceptance may continue with a clearly
unestablished date. Existing historical dates are retained as unverified. Calendar revision
publication does not retroactively change accepted filings or cases. This is not a deadline calculator.

- `GET /api/v1/courts/{id}/calendars`: public revision history, 25 per page, and the viewer's
  publication permission.
- `POST /api/v1/courts/{id}/calendars`: court-scoped publication of a retained revision.
- `GET /api/v1/courts/{id}/filing-date?received_at={ISO_timestamp_with_offset}`: read-only
  preview; it does not alter a filing or create an official receipt.

Migration `a8b712e43c90` adds calendars, envelope date assessments and case filing dates.
SQLite and PostgreSQL triggers reject calendar UPDATE and DELETE, including in schemas
created through Alembic. The migration does not invent calendars or backfill historical
filing dates, and refuses an automatic downgrade that would erase these records.
`backend/tests/test_court_calendars.py` covers midnight, daylight-saving transitions,
different court timezones, holidays, adjacent years, revisions, permissions and receipt
preservation. The migration and PostgreSQL suites cover the retained records as well.

### Recording signed filing-date orders

Assigned clerks, judges and court administrators can open **Record a filing-date order**
from a filing's private history. The form requires a readable PDF of an existing signed
order, its signing date and reference, the ordered filing date, the reason, and an explicit
attestation that staff reviewed the order. Recording requires a court assignment; being a
system administrator alone is insufficient. Drafts and service-only records are ineligible.
An order can be recorded against a pending, accepted, returned or rejected submission;
this action does not accept or reopen it. Legacy records keep missing receipt times missing.

This supports recording the outcome of a court procedure. MCR 1.109(G)(7)(a) permits a
motion for a court order establishing an earlier filing date after a transmission failure,
subject to findings by the court. MUEFS does not decide those findings, calculate relief,
authenticate a signature, or infer an earlier date from an outage. The same recording path
can retain another authorized date decision after the court follows its applicable procedure.

The `filing_date_ordered` transaction retains the previous date and basis, the new ordered
date and reference, the actor, UTC decision recording time and signed PDF manifest. Earlier
transactions and file bytes remain intact. The original receipt timestamp is never changed.
The signed PDF initially has restricted access for the filer and assigned court staff;
staff can use the existing public-copy workflow to publish a reviewed copy on the accepted
case docket. Court orders are excluded from filer attachment manifests and cannot be
uploaded or removed through the filer's document controls. Recovery audits include their
retained manifests. Acceptance verifies the current order's stored bytes as well as the
filing attachments and preserves the ordered date; the CMS acceptance boundary still applies.

Staff must explicitly select applying the same order to an existing case's opening date.
The case's original `filed_date` instant stays unchanged. No relationship to a historical
initiating filing is guessed. Acceptance of a new case uses its envelope's ordered filing
date. A later corrected submission receives a fresh calendar assessment; the prior order
stays attached to its original submission attempt and is not silently carried forward.

Filing and case date versions reject stale decisions, including a form opened before
acceptance creates a case. Account and court authority are checked again after PDF inspection,
then locked through the transaction. Competing orders for one filing, or different filings
changing one case date, cannot both overwrite the same version. Date, order metadata,
receipt, notice and audit writes share one database transaction; failed writes remove the
newly uploaded candidate. Document inspection and upload happen before these record locks.
The docket loads documents and public copies in batches, including court orders without
adding them to the filer's relationship or serializing hidden originals into public responses.

- `GET /api/v1/clerk/filings/{id}/filing-date`: private current date, basis, receipt,
  case opening date, versions and eligibility.
- `POST /api/v1/clerk/filings/{id}/filing-date`: multipart signed order and decision,
  with `expected_version` and, for a case change, `expected_case_version`.

Migration `b2e4a8c19d70` adds the two version counters without changing historical dates.
The order documents and append-only transaction tables are reused. An automatic downgrade
is refused to prevent a previous application version from ignoring retained court orders.
Twelve workflow and PostgreSQL concurrency cases cover receipt preservation, date/version
conflicts, publication, legacy records, resubmission, corruption, rollback and authority
changes. The full local backend suite passes 274 tests with PostgreSQL and S3-compatible
storage enabled. Five browser checks exercise the form, download fingerprints, acceptance,
stale edits, case dates and the public docket at desktop and mobile sizes.

## Filing notice email

`EMAIL_DELIVERY_ENABLED` defaults to false. When enabled, a filing transition creates its
portal notice and a generic email in the same transaction. The request performs no SMTP
work. The queued message contains an authenticated portal link and notice reference;
case captions, decision reasons, financial information and attachments stay in the portal.
The destination survives demo sign-in, the OIDC callback and expired-session redirects;
external destinations and sign-in loops are rejected.

Successful OIDC authentication records a verified email only when the claim matches the
account address. Missing, changed or unverified claims remove that verification. Existing
accounts and demo role headers do not invent verification. The worker rechecks the active
account and matching address immediately before sending. Blocked recipients remain visible
in **Notices** and can be retried after verification.

Run `python -m app.notification_worker` in a separate process with the API's database and
mail settings. `--once` drains messages currently due and exits. PostgreSQL workers claim
independent rows with `SKIP LOCKED`; the claim and started event commit before network I/O.
The database connection is released during SMTP. Automatic retries preserve the original
message and Message-ID, with at most five attempts and delays of 2, 4, 8 and 16 minutes.

A successful final SMTP response records **Accepted by email relay**, not inbox delivery.
A refused message records a temporary or permanent failure. A lost final response, or a
started attempt without an outcome after ten minutes, becomes **Email outcome unknown**.
These messages are not automatically resent. Assigned court staff must inspect relay
records and give a reason before queuing another email. This avoids claiming exactly-once
delivery where SMTP and a database cannot provide it. Late workers cannot overwrite a
newer retry. Recipients can retry confirmed failures; they cannot resend accepted or
uncertain messages themselves.

`/notifications` provides paginated personal and court-scoped notice lists, status filters
and private delivery history. Retry requests are serialized and logged with the operator's
reason. Queued events preserve the exact message; attempt events retain times and SMTP
response codes. SQLite and PostgreSQL triggers reject event updates and deletion. This
archive still requires production database privilege controls and protected backups.

Migration `b51d804a3e62` adds verification, outbox fields and delivery events. It leaves old
pending notices portal-only and archives earlier sent/delivered/failed claims as unverified
historical statuses. Enabling email does not send an old backlog. Fabricated notification
seed data has been removed. The migration refuses an automatic downgrade that would erase
transport evidence.

The local SMTP tests exercise actual wire exchanges, rejection, lost final responses,
retry timing, privacy, TLS refusal, recipient verification and rollback. PostgreSQL tests
cover competing workers and retention guards on both fresh and migrated schemas. Relay
acceptance is not a bounce report, proof of reading, a service certificate, or a waiver
decision deadline trigger. Those court procedures remain separate implementation work.

## Identity administration and court access

**People & access** provides a paginated identity directory, provisioning, identity-subject
binding, account deactivation and court grants. System administrators manage identities
and delegate administration for named courts. Court administrators see only their courts'
assignments and change history. An exact-email lookup can find an already provisioned
clerk or judge for assignment without exposing the statewide directory or other courts'
grants. Delegates cannot edit identity subjects, verify bar numbers, create accounts or
assign administrator privileges. A judicial grant requires a judge account.

The first administrator is bound by `python -m app.admin_bootstrap` from an authorized
database operator session, with a retained bootstrap event. Later changes require an
authenticated system administrator. Active accounts require an IdP subject outside demo
mode. Email verification can only come from matching verified IdP claims; it cannot be
invented by a directory edit. A changed address or subject, or deactivation, clears it.
Bar verification is an explicit human assertion using a court-approved source, not a
connection to a bar registry or proof of current standing.

Account changes and court grants retain the operator, reason, UTC time and before/after
values in the same transaction. A version check rejects stale forms. Concurrent PostgreSQL
requests recheck administrative authority after taking locks. Self-revocation and changes
to one's own system identity binding require another administrator. Staff grants must be
revoked before an account type changes, preventing a later type change from retaining
unintended judicial authority. Disabling an account or revoking a grant denies subsequent
protected requests even with a still-valid token. Cached navigation refreshes on sign-in;
already downloaded records and work already authorized are outside that revocation boundary.

Mutations lock only the actor and affected account, rather than every system administrator.
Authentication can also update an actor's verified email; if those earlier writes cause
overlapping changes to deadlock, the API rolls back the losing operation and returns a
conflict requiring refresh. It does not replay an authority change automatically. The
concurrency tests force this overlap with both fresh and previously verified identities.

Database retention now covers the audit log itself, including raw SQL updates and deletes.
One shared model helper replaces repeated trigger definitions and the ORM hook that scanned
all dirty objects while missing bulk SQL. Migrations preserve their own frozen definitions.
Migration `d26e49b73c18` archives duplicate grant identifiers and timestamps before enforcing
uniqueness, adds an index for per-account history, and refuses a destructive downgrade.
Database ownership and TRUNCATE privileges must remain outside the runtime role.

Directory pages fetch court grants in one batch. System statistics now use one database
round trip for five counts. The administration page loads only when opened. Production
login no longer displays demo identities or invents a court assignment for unassigned
staff; production tool discovery also excludes unavailable demo sign-in tools. The browser
security policy allows token exchange with the configured IdP origin while retaining the
separate restrictive API policy.

Verification includes administration permissions, rollback with an audit failure, stale
versions, first-administrator bootstrap, legacy migration and concurrent requests against
PostgreSQL on model-created and migrated schemas. A local Keycloak 26.7.3 realm exercised
real browser PKCE, provisioning, delegation, existing-token revocation, deactivation,
private history and responsive layouts with demo authentication and auto-provisioning off.
The local HTTP test realm and synthetic appointments are not a production identity review.
State federation, MFA and session policy, signing-key rotation exercises, lifecycle imports,
access recertification and recovery drills remain implementation work with the court.
The current frontend keeps bearer tokens in browser storage; the production identity review
must address that session design and XSS exposure. An IdP cookie does not itself establish
an application session for this API.

## Court-managed participants and restricted-case access

**Court Cases** lists public and sealed matters only for a staff member's assigned court,
with an exact case-number lookup and 25-record pages. The case docket links assigned staff
to **Manage participants**. Staff can record a party or counsel, identify a represented
party, link an existing account and explicitly grant restricted-case access. Generic
attorney roles accommodate representation that is not accurately described as plaintiff
or defendant. Retiring a record preserves it as former participation and removes its grant.

Acceptance previously inferred every filer to be a plaintiff or plaintiff's attorney and
independently granted accepted filers access to sealed dockets. Both paths are deleted.
An accepted envelope proves that a filing was accepted; it does not identify the filer's
capacity or authorize all case records. Filers retain their own envelopes and receipts.
Counsel grants now require an explicit account link and the account's current verified,
matching bar number. A public bar-number match never links an account automatically.

All staff changes require a reason and court authority/reference. Actor and case locks
recheck current authority, and a case version rejects an obsolete editor. A failed audit
write rolls back the participant change. Audit history retains the operator, UTC time,
reason and before/after values. Staff cannot change their own participant record. A system
administrator also needs an assignment at the case's court to manage participants.

Migration `e83f2c91a6d4` preserves all legacy participant records and private contacts,
adds a per-case review-needed event, and starts those rows without an access grant. Court
review is required before enabling them. Multiple active records can legitimately grant
the same account access; retiring one record does not remove independent grants or court
roles. Current access is checked on subsequent protected requests, including favorites.
The public docket exposes participant names, roles and representation, but excludes linked
accounts, contact details, access flags and private administrative history.

The court directory uses the `(court_id, id)` index and seeks from the last displayed ID
instead of scanning an offset or counting every case. Participant account emails load in
one joined query per page. Case-insensitive account lookup uses an expression index and
rejects ambiguous legacy identities. Staff docket views no longer request favorites, and
the new court screens load only when opened. The CORS policy now permits `PUT` for staff
edits on deployments with separate frontend and API origins.

Verification covers grant/retirement, retained private access, counsel identity checks,
cross-court denials, ambiguous identities, pagination, stale edits, failed audit rollback,
historical migration and PostgreSQL concurrency on fresh and migrated schemas. Local
Chromium exercises the staff workflow, public-search boundary and desktop/mobile layouts.
These administrative records do not establish legal appearance, approve withdrawal,
replace the court's system of record, or enroll anyone in electronic service. A court
must approve the access policy and migration review before operational use.

## Court-reviewed public copies

Assigned staff open **Manage public access** from a docket document or a filing receipt.
They can withhold public access immediately with a recorded reason/authority, prepare a
separate PDF with its approved public title, and download that exact candidate for review.
Preparation alone grants no public or filer access to the candidate. Publishing requires
an explicit review confirmation and reason/authority; the service rechecks the stored
candidate's SHA-256 before changing access. Only a current document on an accepted filing
linked to a case can receive a public copy. Fee-waiver applications and orders are excluded.

Publication atomically restricts the original and selects the reviewed copy. The public
case docket returns only the derivative's title, size, page count and hash. Neither
publication nor withdrawal rewrites the original's bytes, title, fingerprint or retained
receipt. Withholding clears the active copy and keeps the original restricted. It never
automatically restores access to an unreviewed original. The filer retains access to copies
that were actually published, including after withdrawal; only assigned court staff can
inspect never-published candidates. Sealed-case restrictions still govern other viewers.

Actor, filing and document locks recheck current staff authority after slow file inspection.
A per-document version rejects stale edits. Publication and withholding commit their audit
event, filing transaction and notice together; a failed record write rolls back the access
change. Audit history snapshots the staff member's name and retains reasons, UTC times and
before/after access. Migration `f94c81e2b7d5` adds retained public-copy records with
append-only PostgreSQL/SQLite guards. It does not rewrite existing originals or infer
publication approval. An automatic destructive downgrade is refused.

The docket loads copies in one query for the displayed page, with no extra copy query for
staff/filer original views or pages without copies. Regression checks at 3 and 25 documents
verify a single copy query and no off-page copy materialization. The publication screen
loads as a separate bundle, and its access history loads only when expanded. Upload
inspection and streaming downloads share the existing bounded paths; integrity checks read
64 KiB chunks. Missing local/S3 objects now return unavailable-file responses instead of a
fabricated simulated document page. API responses prevent storage in HTTP caches; a
withdrawal affects subsequent requests and cannot recall an already downloaded file.

Verification covers preparation warnings, exact public bytes and metadata, unchanged
receipts, original access, withdrawal, wrong-document copy IDs, missing storage, malformed
PDFs, audit rollback, retained actor names, pagination and sealed-case restrictions.
PostgreSQL checks on model-created and migrated schemas cover competing publish/withhold
decisions, append-only records and revocation while integrity inspection is pending.
Local Chromium exercises staff preparation/review, public and filer downloads, stale
edit rejection, history loading and desktop/mobile layouts using synthetic records.

Michigan's [Trial Court Records Management Standards](https://www.courts.michigan.gov/4a81cf/siteassets/court-administration/standardsguidelines/casefile/cf_stds.pdf)
distinguish protected records from public copies and require attention to restricted
information. This workflow supplies a review mechanism; it does not determine whether a
specific record may legally be released. Staff must review the complete PDF, hidden text,
annotations and metadata using approved tools. The existing PII check samples text from
at most five pages and cannot prove that redaction is complete. A complete classification
matrix, court-authorized release policy, file-stamped derivatives, retention/disposition
procedures and storage/recovery validation remain outside this implementation.

## Stored-file integrity and validation cost

Submission, service-only recording and acceptance stream every current attachment before
recording the transition. Both SHA-256 and actual byte count must match the uploaded record.
Missing objects, storage failures and mismatches return HTTP 409 without changing filing
status, reviewer fields, receipts or CMS acceptance. Rejection and return remain possible.
The clerk queue retains the specific document and recovery guidance in its error panel.
An already completed idempotent submission retry returns its existing result without
reading files or creating another receipt.

PDF uploads must be readable. Their sampled PII screening warnings are saved once and
reused during advisory validation, removing the previous whole-file reads and repeated
PDF parsing. Migration `a71b03d9e6f2` preserves legacy records with a null screening result;
validation explicitly asks for review instead of treating unknown history as a clean scan.
The scan still samples at most five pages, performs no OCR or redaction, and cannot prove
that a document is free of protected information.

A local comparison against commit `ec8f0d5`, using sixteen five-page PDFs totaling 322,110
bytes and the median of five warmed samples, measured:

| Operation | Median | File reads | PDF parses |
| --- | ---: | ---: | ---: |
| Previous advisory validation | 194.821 ms | 16 | 16 |
| Validation using retained screening | 2.560 ms | 0 | 0 |
| Required streaming integrity pass | 13.693 ms | 16 | 0 |

These are synthetic local-filesystem measurements, not production load or S3 latency
evidence. Integrity reads use 64 KiB chunks in worker threads. A shared actor lock keeps
authority stable during the transition while allowing unrelated filings and foreign-key
references; ordered envelope locks avoid reversed batch lock acquisition. Account and
court-role administration remain serialized with these transitions. PostgreSQL's
[row-lock conflict rules](https://www.postgresql.org/docs/16/explicit-locking.html#LOCKING-ROWS)
inform that choice; concurrency tests exercise the actual request behavior.

Regression checks cover same-length corruption, wrong recorded sizes, missing files,
storage outages, retry after restoration, idempotent replay, partial batch success,
responsive health requests during slow reads, account revocation after authentication and
same-filer uploads during another submission. Transition fixtures now store real bytes;
search and SMTP tests no longer run irrelevant filing/acceptance workflows. Fresh demo
seeds generate marked synthetic PDFs with matching metadata. Existing retained records
are preserved and are never silently rewritten to match newly fabricated files.

This verifies integrity at the transition, not continuing storage immutability. Court
storage permissions, versioning, backup/restore, retention and reconciliation procedures
remain necessary. Full document review and the separate CMS, payment and electronic-service
integration requirements remain unresolved.

## Recovery verification

The [storage recovery audit](STORAGE_RECOVERY.md) checks all current and archived document
rows, private court decisions and prepared public copies, including withdrawn copies.
It also compares submission, service-recording, fee-waiver and publication snapshots with
current file metadata. It cannot silently accept hashes changed to conceal altered bytes
when the retained transaction records a different fingerprint. Reports stream as JSON Lines,
omit private titles/keys and distinguish complete, discrepant and incomplete runs.

A local PostgreSQL/S3-compatible exercise restored a custom-format database backup and
seven files into separate targets. Six transaction references and every detailed file
result matched the source. Read-only audit accounts were denied writes. Corruption,
matching changes to mutable metadata, a missing withdrawn copy and denied storage access
produced failing reports; restoring backup data reproduced the source results. Regression
coverage includes batched metadata paging and real concurrent/multipart S3 transfers.

The command uses a database read snapshot, bounded metadata batches and 64 KiB storage
reads. Receipt comparisons do not download the files again. Reusing the S3 client's
connection pool reduced a seven-small-PDF verification pass from a 123.387 ms median to
10.765 ms over five warmed local samples against commit `84e7ce0`. These measurements
exclude process startup and do not establish production latency or statewide capacity.

Full restore evidence still requires comparison with the backup inventory, recovery of
non-file database records, protected object versions, court retention policies and tested
recovery targets. A matching audit of an incomplete database cannot prove that omitted
records never existed. The tool does not repair data or decide which objects may be deleted.

## Sources guiding the evaluation

- [RFC 5321, SMTP](https://www.rfc-editor.org/rfc/rfc5321): relay acceptance, response codes and uncertainty after a lost final response.
- [Python SMTP client documentation](https://docs.python.org/3/library/smtplib.html): TLS, envelope commands, timeouts and transport exceptions.
- [Keycloak upgrade guidance](https://www.keycloak.org/docs/latest/upgrading/index.html): the `basic` client scope and subject mapper needed when configuring current access tokens.
- [Browser connection policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/connect-src): allowing the configured identity provider for browser token exchange.
- [Michigan Court Rule 1.109, electronic filing and service](https://www.courts.michigan.gov/siteassets/rules-instructions-administrative-orders/michigan-court-rules/court-rules-book-ch-1-responsive-html5.zip/Court_Rules_Book_Ch_1/Court_Rules_Chapter_1/Court_Rules_Chapter_1.htm): transaction records and notices, filing timing, service and transmission failures.
- [Michigan Court Rule 2.002](https://www.courts.michigan.gov/siteassets/rules-instructions-administrative-orders/michigan-court-rules/court-rules-book-ch-2-responsive-html5.zip/Court_Rules_Book_Ch_2/Court_Rules_Chapter_2/Court_Rules_Chapter_2.htm): waiver requests, nonpublic information and court decisions.
- [Michigan Court Rule 2.117](https://www.courts.michigan.gov/siteassets/rules-instructions-administrative-orders/michigan-court-rules/court-rules-book-ch-2-responsive-html5.zip/Court_Rules_Book_Ch_2/Court_Rules_Chapter_2/Court_Rules_Chapter_2.htm): appearances, limited-scope representation and withdrawal require their applicable court procedures.
- [NCSC electronic filing process standards](https://www.ncsc.org/__data/assets/pdf_file/0022/15367/recommended_-process_-standards_02_26_03.pdf): historical functional guidance on document integrity, security and transaction records; not a current product certification.

These sources guide implementation requirements. A participating court must validate the
applicable rules, policies, pilot orders and integration contract before any real filing.
