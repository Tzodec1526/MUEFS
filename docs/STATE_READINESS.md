# State implementation evaluation

MUEFS remains a proof of concept. The objective is an efiling suite that can withstand a
state's implementation evaluation, including actual filing operations, integrations,
security, accessibility, and recovery. Passing a demo or this repository's tests does not
establish state approval or production readiness.

## Operating requirements and current evidence

| Requirement | Current evidence | Remaining work |
|---|---|---|
| Prove what was submitted | Each new submission has a retained transaction ID, UTC receipt time, filer name, document manifest and SHA-256 fingerprints, payment reference where present, and a downloadable receipt. | Court-approved retention schedules, trusted time monitoring, external archival controls and production storage verification. |
| Preserve corrections and decisions | Corrections create another numbered submission. Earlier document bytes remain downloadable by the filer and court staff. Acceptance, return, rejection and CMS failure are separate retained events. | Effective filing-date decisions, judicial relief for transmission failures, and certified/file-stamped copies. |
| Survive retries and simultaneous actions | Optional UUID `Idempotency-Key` on submission prevents duplicate receipts. PostgreSQL row locks refresh previously read state. Batch review uses a savepoint per filing. | Operational load tests, outages during real downstream submission, and end-to-end reconciliation. |
| Protect private material | Private envelopes and receipts require filer or court-staff access. Dockets exclude waiver application data, confidential document metadata, superseded documents and other filers' drafts. Fee-waiver documents are nonpublic even if the filer omits the checkbox. | Full classification/retention policy for every case and document type; independent security assessment. |
| Record the correct legal filing date | Each submission's actual receipt time is preserved independently of later clerk decisions. | Court timezones, approved holiday/closure calendars, business-day rules and authorized date adjustments. The UI does not promise that correcting a document preserves its legal filing date. |
| Resolve fee waivers correctly | A completed application accompanies the filing. Clerk waivers, referral and judicial decisions are separate court-scoped actions. Signed decision PDFs and denial amounts remain in private history; a filer can pay after denial without resubmitting. | Actual notice delivery, de novo review and judicial assignment, court calendars/deadlines, case-wide continuation and reinstatement, court verification of signed forms and prisoner-specific procedures. |
| Collect and reconcile funds | Demo fee quoting, simulated payments and linked payment references work. | Audited court fee schedules, a real hosted payment processor, signed webhooks, reconciliation, refunds and accounting exports. |
| Deliver electronic service | Service-only documents can be recorded. | Verified service contacts, consent/eligibility, real transmission, failures/retries, non-electronic alternatives and retained proof. A recorded document or in-app notice is not proof of service. |
| Connect to the court's system of record | Acceptance is explicitly blocked outside demo mode when CMS integration is absent. | A documented court/vendor contract, credentialed sandbox, document/code mapping, idempotent delivery, status callbacks, error recovery and reconciliation. |
| Operate statewide | Court-scoped access, PostgreSQL support, migrations, health checks and deployment guidance exist. | Identity lifecycle and delegated administration, availability targets, incident response, backup restoration drills, disaster recovery and migration from incumbent systems. |
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
policy before production use. In-app notices are available; email transmission is not.

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

After denial, the filer can record a simulated payment of the amount in the decision from
history. The server uses that amount, including on a corrected filing, instead of applying
a subsequently changed fee schedule. Payment creates its own receipt and does not change
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

## Sources guiding the evaluation

- [Michigan Court Rule 1.109, electronic filing and service](https://www.courts.michigan.gov/siteassets/rules-instructions-administrative-orders/michigan-court-rules/court-rules-book-ch-1-responsive-html5.zip/Court_Rules_Book_Ch_1/Court_Rules_Chapter_1/Court_Rules_Chapter_1.htm): transaction records and notices, filing timing, service and transmission failures.
- [Michigan Court Rule 2.002](https://www.courts.michigan.gov/siteassets/rules-instructions-administrative-orders/michigan-court-rules/court-rules-book-ch-2-responsive-html5.zip/Court_Rules_Book_Ch_2/Court_Rules_Chapter_2/Court_Rules_Chapter_2.htm): waiver requests, nonpublic information and court decisions.
- [NCSC electronic filing process standards](https://www.ncsc.org/__data/assets/pdf_file/0022/15367/recommended_-process_-standards_02_26_03.pdf): historical functional guidance on document integrity, security and transaction records; not a current product certification.

These sources guide implementation requirements. A participating court must validate the
applicable rules, policies, pilot orders and integration contract before any real filing.
