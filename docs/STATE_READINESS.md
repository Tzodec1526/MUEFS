# State implementation evaluation

MUEFS remains a proof of concept. The objective is an efiling suite that can withstand a
state's implementation evaluation, including actual filing operations, integrations,
security, accessibility, and recovery. Passing a demo or this repository's tests does not
establish state approval or production readiness.

## Operating requirements and current evidence

| Requirement | Current evidence | Remaining work |
|---|---|---|
| Prove what was submitted | Each new submission has a retained transaction ID, UTC receipt time, filer name, document manifest and SHA-256 fingerprints, payment reference where present, and a downloadable receipt. A read-only recovery audit compares stored bytes and retained transaction references. | Court-approved retention schedules, trusted time monitoring, external archival controls and validation of the deployed storage/recovery configuration. |
| Preserve draft work | Account saves, filing-specific recovery within a verified account/tab, explicit conflict comparison and cross-tab identity invalidation are implemented. Creation keys recover lost initial responses; PostgreSQL concurrent saves preserve the winning version. | Broader offline/device testing and assistive-technology evaluation. |
| Preserve corrections and decisions | Corrections create another numbered submission. Earlier document bytes remain downloadable by the filer and court staff. Acceptance, return, rejection, CMS failure and signed filing-date orders are separate retained events. | Court procedures for deciding relief, certified/file-stamped copies and court-approved retention. |
| Route filings to the correct court and case | Creation and submission validate the filing kind, court, case type, existing case and current filer access. Court administrators publish intake availability and public instructions with retained reasons, authority and version conflicts. Valid received work remains reviewable after intake closes. | Court-approved closure and reopening procedures, reconciling legacy assignments and correcting a filing's destination without losing its retained evidence. |
| Survive retries and simultaneous actions | Database commits finish before HTTP success responses. Submission requires the version of the details, active documents and fee state the filer reviewed. Optional UUID `Idempotency-Key` on submission prevents duplicate receipts. PostgreSQL row locks refresh previously read state. Review decisions identify the numbered submission the reviewer saw; an intervening resubmission invalidates that decision. Batch review uses a savepoint per filing and reports each failed item. | Operational load tests, outages during real downstream submission, and end-to-end reconciliation. |
| Locate and assess received work | Assigned staff search the review queue by case title/number or exact filing number and filter by status and elapsed receipt age. Counts cover all matching pages; oldest-first reads use an index for pending work. | Court-approved intake priorities, staffing procedures, representative load testing and independent accessibility evaluation. Elapsed age does not establish a deadline violation. |
| Publish reviewed public copies | Assigned staff prepare and inspect a separate PDF and public title, explicitly publish it, and withdraw public access with retained authority/history. Originals and receipts stay intact; fee-waiver records cannot use this publication path. | Court-approved classification/redaction policy, approved review tools, storage immutability and retention schedules. |
| Screen incoming documents | Every upload uses the shared inspected path. Enabled ClamAV scanning requires a complete verdict within one deadline; failures/cancellation cannot store a document. Production startup, private scanner networking, explicit limits and a guard against oversized compressed members are implemented and tested against ClamAV 1.4.6. | Court-approved file/complexity policy, current signature operations, legacy-document review, representative load and independent security validation. A clean verdict does not certify a document safe. |
| Protect private material | Private envelopes and receipts require filer or court-staff access. Dockets exclude waiver application data, confidential document metadata, superseded documents and other filers' drafts. Fee-waiver documents are nonpublic even if the filer omits the checkbox. | Full classification/retention policy for every case and document type; independent security assessment. |
| Control case participation and access | Assigned staff record participants, counsel representation and explicit restricted-case grants with retained reasons, before/after history, stale-edit checks and revocation. Filing acceptance no longer assigns party roles or grants case access. | Court-approved access rules, review of legacy records, CMS appearance/withdrawal synchronization, limited-scope representation and service enrollment. |
| Record the correct legal filing date | Receipt instants and filing dates are separate. Published calendars establish business dates. Assigned staff can record a signed order establishing a different date, with retained before/after evidence and explicit case opening date changes. Acceptance honors the order without rewriting the receipt. A correction keeps the filing date, and an order stays on the filing. | Court verification of calendars and signed orders, motion/adjudication procedures, downstream CMS synchronization and review of closures published after acceptance. |
| Resolve fee waivers correctly | A completed application accompanies the filing. Clerk waivers, referral and judicial decisions are separate court-scoped actions. Signed decision PDFs and denial amounts remain in private history; a filer can pay after denial without resubmitting. | Actual notice delivery, de novo review and judicial assignment, deadline calculation, case-wide continuation and reinstatement, court verification of signed forms and prisoner-specific procedures. |
| Establish fees and account for payments | Assigned staff record itemized assessments. Separately assigned court administrators can credit verified external receipts, reverse erroneous credits and retain the source evidence. Balances preserve partial payments and expose overpayments after reassessment. A private court receipt register provides period totals, recorded activity and bounded CSV exports. | Court validation of assessments and source receipts, independent reconciliation and correction review, a hosted payment processor, signed webhooks, refunds and accounting-system mappings. |
| Deliver electronic service | Staff review service instructions. Senders explicitly select retained subsequent documents and eligible recipients; immutable packages retain contents and addresses. An opt-in SMTP outbox queues protected links, rechecks instructions and records failures/retries. Recipients download only selected, verified bytes and can acknowledge the package. | Court-approved enrollment, consent and confidential-document policy; additional/delegated recipients; bounce feedback and failed-service remedies; non-electronic evidence and certified proof. Relay acceptance and download requests do not establish legally sufficient service. |
| Send filing alerts reliably | An opt-in SMTP outbox commits with filing changes, checks verified recipients, retains messages and attempts, retries temporary failures and exposes uncertain outcomes to assigned court staff. | A court-approved relay and sender domain, bounce/delivery feedback, operational alerting and court approval of legally sufficient notice content and procedures. Generic email alerts do not establish legal service. |
| Connect to the court's system of record | Without CMS integration, acceptance outside demo mode is records-only: MUEFS assigns the case number and records no CMS identifier. | A documented court/vendor contract, credentialed sandbox, document/code mapping, idempotent delivery, status callbacks, error recovery and reconciliation. |
| Operate statewide | Explicit identity provisioning, delegated court administration, immediate checks on subsequent requests after revocation, retained changes, PostgreSQL migrations and deployment guidance exist. | State federation and lifecycle integration, access recertification, availability targets, incident response, backup restoration drills, disaster recovery and migration from incumbent systems. |
| Find public records across courts | Anonymous search filters by court and identifies each result's court and county. Shared links preserve filters and pages; courts with closed intake remain searchable. PostgreSQL substring indexes and batched court metadata improve selective searches while excluding sealed cases and participant contact fields. | Representative concurrency, data-distribution and write-load testing; independent accessibility evaluation and court-approved public-index policy. |
| Transfer a case's retained records | A private case archive includes linked metadata, transaction history, original versions, orders, public copies, payments and notice evidence. A read-only snapshot and file fingerprints protect export consistency; offline verification detects altered or incomplete packages. | Court-controlled custody/signing, source inventory reconciliation, receiving-system mapping, approved retention and an evaluated import/restore procedure. |
| Serve the whole public | Responsive filing and history pages, keyboard controls and guided filing exist. | Independent accessibility testing, assistive-technology testing, language access, paper-filing accommodations and usability evaluation with self-represented filers. |

## Draft editing and recovery

On the details step, **Save draft** saves the title and description to the filer's account.
**Continue** also saves before advancing. New saves acquire a filing ID; later saves use
that same filing. **My filings → Continue filing** resumes the account's saved record,
including from a browser with no local recovery data.

Creation requires a UUID `Idempotency-Key` on `POST /api/v1/filings`. The browser saves
that key with the local draft before sending and keeps it when retrying or reloading.
The API retains the key and a fingerprint of the validated creation fields on the filing,
with a unique index scoped to the filer. New creation returns 201; the same request
returns 200 with the current filing, including later changes. Replay does not repeat the
creation audit entry or reopen a submitted filing. It works after intake closes, while
still requiring an active account permitted to manage filings.

Reusing a creation key with different details returns 409 and the existing owned
`filing_id`. The editor carries the unsaved text into that filing's comparison view;
it never replaces newer details automatically. If local recovery storage refuses the
transfer, the text stays on screen with a link to the saved filing and copying guidance.
Changing the destination requires starting a separate filing. Inputs stay disabled during
the save, and navigating away leaves recovery intact without a late response redirecting
the user back into the editor.

An envelope response includes `details_token`. A `PATCH /api/v1/filings/{id}` that changes
`case_title` or `filing_description` must supply its opened version as
`expected_details_token`. Missing/malformed preconditions return 422. The API compares
the token under the filing's existing row lock and returns 409 when the saved details,
status or numbered submission changed. The token is derived from those values, so no
schema migration or separate version counter is needed. Unrelated fee changes leave it
valid; document, fee and submission operations retain their separate checks.

On conflict, the interface preserves the entered text, shows it beside the saved version
and moves keyboard focus to the comparison. The filer chooses the saved details or keeps
their edits for a subsequent explicit save. Reloading preserves an unresolved comparison.
Once a filing has been submitted, recovered text stays available for copying and history
remains accessible; it cannot be saved into that received filing.

Recovery uses versioned `sessionStorage` entries for each verified account and filing.
It stores form fields and their original details token, omitting document lists and
payment state. Different tabs have independent recovery storage. Account changes in
another tab invalidate the old screens and reverify the identity; signing out clears
the current tab's recovery entries. A legacy browser entry associated with a saved filing
is offered only after the server verifies ownership, and its unknown base requires
comparison. Unscoped entries without a verifiable saved filing are left unadopted.

Recovery is limited to the browser's tab session. Save to the account before closing
the tab or switching devices. The interface warns about unsaved changes and storage
refusal; browser recovery cannot guarantee survival of crashes, cleared data or closed
sessions. Failed saves retain the form text and creation key. If that recovery is gone,
check My filings before starting a separate draft; a new request key means a new filing.

Verification reproduced a stale tab overwriting a newer save before the fix, and a live
tab retaining the previous account's editor after a cross-tab identity change. API tests
now cover required preconditions, PostgreSQL simultaneous saves, fee independence and new
submission cycles. Rendered checks exercised new creation, separate filing recovery,
offline failures, storage refusal, legacy recovery, desktop/mobile comparison and account
switching. In a synthetic 24-document filing, the recovery payload decreased from 2,327
to 374 bytes (about 84%); this is a storage/serialization measurement, not a typing-latency
or statewide load benchmark.

Creation verification covers simultaneous PostgreSQL requests with matching and conflicting
details, per-account key isolation, later edits/submissions and closed intake, one creation
audit entry, and recovery from a failed concurrent index build. Browser checks drop actual
committed responses and exercise reload, changed text, a request that never reaches the
server, navigation and account switching during saving, storage refusal and desktop/mobile
comparison.

## Court service instructions

Assigned court staff open **Manage case access → Service instructions** to record one
current destination and method for a reviewed participant. An electronic instruction
requires the linked account's current verified email and active identity. Counsel also
need a matching verified bar number; restricted cases require the participant's access
grant. Mail and hand-delivery instructions support people without portal accounts.
Staff record the reviewed authority or source record and a reason for every change.

Contact and participant versions prevent stale editors from overwriting reviewed work.
Changed participant details or electronic identity/access prerequisites appear as review
issues. Deactivation remains available when an address loses verification. Changes retain
their actor, time, authority, participant snapshot and prior destination in case history
and private case exports. Staff cannot edit their own service instructions. Editing and
full history require assigned court staff; authorized senders see current instructions
when selecting recipients. Editing instructions does not grant portal access or send messages.

Migration `a63b29d5e104` preserves legacy contacts as inactive, unlinked and unreviewed;
it does not infer eligibility from an existing address. The interface currently supports
one primary destination per participant. Additional/delegated recipients, operational
enrollment procedures and failed-service remedies remain required work.

## Selected document delivery

An explicit sender action creates a retained package from the current submission receipt,
with selected document manifests and frozen reviewed recipient instructions. A UUID request
key prevents duplicate packages on replay. Initial-case service uses separate procedures;
fee-waiver material is excluded. Documents are available only to each named account, the
sender and assigned staff, without granting access to the rest of the filing. Current
participant eligibility and restricted-case access are checked on recipient downloads.

`SERVICE_DELIVERY_ENABLED` is a separate, default-off gate and requires the existing SMTP
outbox configuration. The worker rechecks frozen service instructions before transmission.
The interface preserves generic alert status, exact selected documents, download requests
and explicit recipient acknowledgment as separate evidence. SMTP uncertainty requires staff
review before retrying. Changed email instructions require a new delivery; old packages keep
their original addresses and stable account recipients. Private exports include that history.

Assigned staff can also record a later relay or recipient failure report with a source
reference and observation time. It alerts the sender, requires staff review before retrying,
and retains the earlier relay result and acknowledgment. Versioned attempt checks and
idempotent report keys prevent duplicate notices and stale reports replacing newer retries.
This is a court review workflow; automatic provider bounce ingestion remains outstanding.

Automated verification covers real loopback SMTP, PostgreSQL concurrent requests and
append-only guards, SQLite/PostgreSQL migrations and exports, and S3-backed browser downloads.
The production frontend was exercised with synthetic signed identities on desktop and mobile.
This does not establish a legally sufficient service procedure, recipient inbox delivery or
court approval. Bounce ingestion, non-electronic evidence, certified proof and deployed load,
security and accessibility evaluations remain outstanding.

The design keeps instructions, transmission and proof separate. [MCR 1.109(G)(6)–(7)](https://www.courts.michigan.gov/siteassets/rules-instructions-administrative-orders/michigan-court-rules/court-rules-book-ch-1-responsive-html5.zip/Court_Rules_Book_Ch_1/Court_Rules_Chapter_1/Court_Rules_Chapter_1.htm)
addresses authorized recipients, service transactions and undeliverable transmissions.
[AO 2026-3](https://www.courts.michigan.gov/siteassets/rules-instructions-administrative-orders/administrative-orders/aos-responsive-html5.zip/AOs/Administrative_Orders/AO_No._2026-3_%E2%80%94_Establishing_Pilot_Project_for_Implementing_Expanded_Electronic_Service.htm)
applies revised rules to participating pilot courts; this application does not presume
that a court participates or infer legal consent from a portal login.

For compatibility, the existing API/storage status `served` still denotes service-only
document recording. New recordings no longer fabricate a clerk-review timestamp, and
the interface labels them **Service documents recorded**. Historical receipts remain
unchanged. This status must not be used as evidence that documents reached recipients.

## Filing destinations and intake

Each court has a public `/courts/{courtId}/intake` page showing current availability,
instructions and case-type restrictions. An active administrator assigned to that court,
or a system administrator, can publish changes there. Clerk assignment alone does not
grant this power. The court flag, complete case-type selection and public notice publish
atomically with a required reason and authority reference. Closures require public
instructions for filers. Reasons, authority, actor and before/after snapshots are retained
in administrator-only history, loaded on demand in pages of 25 changes.

Publication requires the version the administrator reviewed. Stale versions and changed
case-type lists return HTTP 409 without overwriting another publication. Identical settings
create no revision. Account and court authority are rechecked under a shared user lock;
court and case-type locks serialize publications with filing receipts. A failed audit
commit rolls back the settings, and the API reports success only after commit. If a
response is lost, the editor requires reloading the current settings and reviewing history
before another change. This workflow changes intake immediately; it does not schedule
closures, alter calendars or determine filing deadlines.

New-case requests must explicitly use `filing_type: "initial"` and omit `case_id`.
`subsequent` (the API default) and `service_only` require an existing case. New requests
accept only those three filing kinds. Legacy `motion` records remain readable and
reviewable; new motions use a subsequent filing with the appropriate document type.
The selected case type must belong to the selected court and match an existing case.

Creation, advisory validation and submission check the court's `is_efiling_enabled`
and case type's `is_active` flags. Submission rechecks current routing and case access
even if an earlier validation passed. PostgreSQL shared row locks prevent intake changes
from crossing the receipt commit. Invalid submissions leave the draft, documents and
submission count intact; retries of an already committed idempotency key replay the
existing receipt even after intake closes.

Acceptance rechecks court/case/type consistency for older or imported records before
reading stored documents or calling the CMS. It does not require intake to remain open
or the original filer to retain access. A service-only record cannot be accepted as a
court filing. Invalid destinations produce an actionable single-review or batch error;
return and rejection remain available, and valid batch items can complete. These checks
do not silently repair existing records or change their retained receipts.

Saved filings keep their case-type label when that type is disabled. New filing choices
still list active types only. API, PostgreSQL concurrency and rendered browser checks
cover these boundaries, including configuration changes after validation, stale database
reads, receipt replay, case restrictions and partial batch failure.

Additional PostgreSQL checks cover simultaneous intake publications, authority revocation,
audit commit failure and a closure waiting for a receipt commit. Browser checks cover
public/staff separation, lost-response recovery, conflicting edits and mobile layouts.
These use synthetic courts; real closure procedures and accessibility remain subjects for
independent court evaluation.

## Public search measurements

A local PostgreSQL 16 evaluation used 250,000 synthetic cases, 500,000 participants and
20 courts, including sealed records. Each measurement is the median of five warm runs
after one warmup through the actual search service. These are database/service timings,
not browser latency or a production capacity claim.

| Search | Before | After | Matches |
|---|---:|---:|---:|
| Partial case number | 50.49 ms | 4.70 ms | 1 |
| Selective party name | 121.21 ms | 8.67 ms | 496 |
| Party name within one court | 82.12 ms | 7.82 ms | 25 |
| Broad party name | 117.73 ms | 114.09 ms | 247,423 |
| Recent public cases | 18.93 ms | 21.30 ms | 247,423 |
| One court, no text filter | 10.20 ms | 11.96 ms | 12,371 |

The final queries return the same case IDs, totals and ordering. Court metadata adds one
batched query per populated page. Search reads only the public participant fields.
Query plans confirm trigram index scans for selective text searches. Broad searches
remain scan-intensive; a separate repeated-query check confirmed that transaction-local
custom planning avoids a cached generic plan that roughly doubled their cost. The
setting does not persist into the next transaction. Extra indexes for recent-case
ordering showed no benefit and were not retained.

Verification includes anonymous HTTP requests with duplicate case numbers across courts,
literal wildcard searches, sealed-case exclusion, a complete directory beyond 100 courts,
recovery from a real failed concurrent index build, and migration downgrade/re-upgrade
with records intact. The production frontend bundle was exercised in Chromium for
court selection, pagination, copied links, history/reload, invalid-link recovery and
desktop/mobile layouts. None of these checks establishes statewide load capacity or
independent accessibility conformance.

## Implemented receipt workflow

1. The filer submits an envelope. The application commits its status, receipt and in-app
   notice together before sending a successful HTTP response. The receipt preserves the
   submitted document metadata and payment reference rather than reading those fields
   from the subsequently edited envelope.
2. The filer opens **Receipts and history** from My filings, the submission confirmation or
   a notification. Court staff can open the same history from the review queue.
3. A returned filing can be corrected. Removing a previously submitted document removes
   it from the next attempt, while keeping its stored bytes and original receipt private.
4. Resubmission creates another numbered receipt and keeps the filing date. A clerk decision
   is recorded separately.
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

Review decisions must include the `submission_count` shown when the reviewer opened or
selected the filing. `POST /api/v1/clerk/filings/{id}/review` requires
`expected_submission_count` alongside `action` and any required `reason`. For example:

```json
{"action": "accept", "expected_submission_count": 2}
```

The service compares that number before it reads stored documents, and again with the
refreshed envelope while holding its row lock, before CMS submission or decision records. An
invalid `action` returns HTTP 422. If another reviewer
returned the filing and the filer resubmitted it, the stale decision receives HTTP 409
even though the envelope is again pending. Close the old review, refresh the queue, and
inspect the corrected submission before deciding. Accept, return, and reject all use this
check. The interface displays the submission number and removes a batch selection when
refresh reveals a different submission for that envelope. Opening a different filing
clears the previous filing's review reason and error; clicking the same submission
preserves the reviewer's text.

`POST /api/v1/clerk/queue/batch-review` requires a `filings` list of explicit targets:

```json
{"action": "accept", "filings": [{"filing_id": 123, "expected_submission_count": 2}]}
```

Batch results contain `succeeded` and `failed` ID lists, plus an `errors` object mapping
each failed ID to a message. One stale item does not discard another item's successful
acceptance. Duplicate envelope IDs and missing submission numbers receive HTTP 422.
Legacy envelopes with no numbered submission use their recorded count of zero; clients
must still send it explicitly. Older bare `filing_ids` batch requests are refused.

## Verification and deployment

Behavioral coverage lives in:

- `backend/tests/test_filing_history.py`: receipts, corrections, private access, historical
  downloads, stable paging, SQL retention guards, stale decisions after correction, and
  rollback of a failed batch item.
- `backend/tests/test_filing_concurrency.py`: simultaneous reviews and submission retries
  on PostgreSQL, stale reviews after resubmission, and retention guards on both
  model-created and Alembic-migrated schemas.
- `backend/tests/test_filing_migration.py`: upgrades preserve legacy filings and documents
  without fabricating old receipts. Repeated startup does not duplicate the migration.
- `backend/tests/test_request_transactions.py`: real PostgreSQL deferred commit failures,
  receipt visibility when HTTP headers are sent, idempotent retries, a paused transfer
  sharing a one-connection pool, and cleanup when its client disconnects. These tests use
  the application's transaction dependency instead of replacing its commit behavior.
- `backend/tests/test_demo_isolation.py`: real API requests use the demo database override,
  commit to the visitor's copy, and keep another visitor and the template unchanged.

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

Court staff can select **Pending fee waivers** in the review queue, including waivers on
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
manifest and reason, and places the request in the court's **Fee reviews** queue. It does
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
The balance credits positive, completed payments allocated to that filer; failed, refunded, reversed,
unallocated and other payers' records cannot clear the obligation. Higher reassessments
require only the remaining balance. Lower reassessments expose the overpayment without
inventing a refund. Submission receipts retain the assessment and all allocated payment
records as they existed at submission. Signed waiver decisions remain the basis for waiver
amounts, and a pending application can accompany a submission for court review.

With `EXTERNAL_PAYMENTS_ENABLED=true`, an administrator explicitly assigned to the filing's
court can record an external receipt through **View fees and payments → View payment records**.
The administrator must be someone other than the filer. A clerk/judge assignment or a
system-administrator account without that court's administrator grant cannot create or
reverse credits. The operator records the source system, receipt reference, received time,
USD amount and verification reason, and confirms the receipt's allocation to this filing.
The portal records an operator's verification; it does not contact the source system,
collect funds, verify settlement or issue a refund. A current court assessment or denied
waiver amount is required. Partial credits are supported up to the remaining amount due.

A unique active-receipt index prevents a second credit for the same court, normalized
source name and receipt reference. Source labels must consistently identify the same
accounting system; aliases, split receipts and bulk allocations require court reconciliation.
UUID request keys recover lost responses without another credit or notice. A reversal
retains the original entry and reason, removes its credit from the current balance, and
allows a new credit against that receipt on the correct filing. Already-reversed requests
are harmless retries. PostgreSQL and SQLite guards reject changes to the source evidence,
deletion and reactivation. Earlier submission receipts remain unchanged.

Payments have a separate review version: a credit or reversal invalidates the filer's
final submission review without invalidating the fee assessment. Both versions are checked
before a new external credit. Reversal checks the payment version. Filing history and
private case archives retain credits, reversals and source receipts. The payment list is
private and paginated. PostgreSQL reads it and its payment version under the filing's shared lock.
If it is newer than the displayed balance, the screen requires a fee refresh before another
credit or reversal. The list and assessment editor load only when opened. Outside demo
mode, unavailable simulated card controls are omitted and eligible waiver actions remain.

Michigan's [trial court financial management guidance](https://www.courts.michigan.gov/4abfef/siteassets/publications/manuals/carg/carg.pdf#page=214)
calls for traceable receipts, retained correction records and independent reconciliation.
The court must approve the source records, administrator assignments, correction procedure
and independent review before enabling this workflow. This is an allocation record linked
to the court's accounting system; it does not replace that system's receipt journal.

Demo initial-filing amounts are visibly synthetic examples. Outside demo mode, seeded
amounts and simulated credits cannot satisfy fee requirements: an assessment, applicable
waiver state or service-only filing is required. Real payment processing remains unavailable;
verified external credits can satisfy an assessed amount when enabled. Credits entered
in demo mode remain marked simulated and are excluded from production balances.

`GET /api/v1/filings/{id}/fees` replaces `POST /api/v1/payments/calculate`. It returns the
current fee state and the matching private filing context. Filers request review through
`POST /api/v1/filings/{id}/fee-review`; assigned staff use `GET /api/v1/clerk/fee-reviews`
and `POST /api/v1/clerk/filings/{id}/fees`. Both review mutations require `expected_version`.
`POST /api/v1/payments/process` requires `expected_fee_version` and the exact remaining balance.

`POST /api/v1/filings/{id}/external-payments` requires a UUID `Idempotency-Key`,
`expected_fee_version`, `expected_payment_version` and the verified receipt details.
`POST /api/v1/filings/{id}/external-payments/{payment_id}/reverse` requires the payment
version, reason and explicit review. `GET /api/v1/filings/{id}/payments?page=1` returns 25
records at a time, including reversed and historical simulated records. These records are
available only to the filer and assigned court staff.

Migration `b28e53cad9f4` adds external receipt evidence and the separate payment version.
It leaves historical payment amounts, status, simulation flags and allocations unchanged.
Its unique indexes omit unrelated legacy rows. Downgrade is refused once external credits
or reversal events have been retained. PostgreSQL tests cover fresh and migrated schemas,
competing credits across filings, request replay, revocation while a request waits, and
transaction rollback. Browser verification includes a committed payment with a lost response,
partial credits, source-receipt download, reversal, reallocation and court access boundaries.

Migration `c3d9f06a21b8` preserves only unambiguous historical payment allocations with a
matching payer and marks legacy payments as simulated. It does not fabricate assessment
records or allocation evidence. Ambiguous historical payments require reconciliation.
The migration refuses destructive downgrade. `test_fee_assessments.py` covers the actual
request, assessment, correction, payment and submission workflow; the PostgreSQL suite
also tests duplicate requests, simultaneous document edits, consistent reads and rollback.

## Court receipt register

**Receipt register** in the court workspace lets an active administrator assigned to the
selected court review external credits and reversals across filings. A system-wide role
without that court's administrator assignment is insufficient. The register remains readable
when external payment recording is disabled, so disabling new entries does not hide retained
history. Filers, unassigned users and clerk/judge-only assignments cannot read or export it.

Choose an inclusive period of at most 31 days and an IANA time zone. Dates select when
MUEFS recorded the activity, independently of the source receipt's received time. Local
midnight boundaries account for daylight-saving changes. A reversal appears on its own
recorded day even if the original credit is outside the period. Positive credits and negative
reversals come from retained filing transactions; reasons, operator names and receipt
references are not reconstructed from current user profiles or payment status.

The page shows credits, reversals and net activity for the whole matching period, with
50 entries per page. Simulated entries are excluded by default; including them displays
separate simulation totals. Net activity can be negative and is not an outstanding filing
balance, bank balance or proof of settlement. Changing courts clears the previous court's
rows and filters. Changing filters requires applying them before an export.

`GET /api/v1/clerk/payment-register` requires `court_id`, `date_from`, `date_to` and
`timezone`; optional parameters are `page`, `include_simulated` and `format=json|csv`.
Each response computes totals and rows in one SQL statement. Separate pages and exports
are fresh reads, so concurrent activity can change the result between requests. CSV exports
include the whole matching period, up to 5,000 entries; larger exports are refused with a
request to shorten the period. Export columns retain signed USD cents, event/payment/filing
identifiers, UTC times, source references, simulation flags, reasons and period metadata.

CSV fields are quoted and text resembling a spreadsheet formula is prefixed with an
apostrophe. Source-exact values remain available in JSON and private filing history. Treat
text columns as text when importing; spreadsheet save/reopen behavior varies, as described
in [OWASP's CSV injection guidance](https://owasp.org/www-community/attacks/CSV_Injection).

Migration `c39f64dbea05` adds one partial index over payment-event times and filing/event
identifiers. PostgreSQL builds it concurrently and repairs an invalid interrupted build
on retry; downgrade removes only the index. Receipt text loads only for selected rows.
On a local synthetic PostgreSQL dataset of 400,000 transactions, 20,000 filings and 100
courts, the busiest court's one-day query improved from 10.636 ms to 1.940 ms, and its
eight-day query from 28.857 ms to 7.513 ms. The partial index used 3,883,008 bytes for
57,142 payment events. Small-court queries remained approximately 0.14–0.27 ms. These are
warmed query-plan measurements, not end-to-end latency or production load certification.

API and PostgreSQL checks cover signed totals above 32-bit range, court isolation,
simulation separation, period boundaries on 23-hour and 25-hour days, pagination, complete
exports, oversized-export refusal, activity committed between reads, concurrent authority
revocation, and failed-index recovery. The register supports a court's reconciliation procedure; it
does not contact the accounting system or record an independent reviewer's approval.

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
IDs and skipped dates. The envelope stores the first receipt in `filed_at`, and `submitted_at`
holds the latest receipt for the queue. A resubmission records its own receipt but keeps the
filing date. Unless a court order has established the date, acceptance reassesses the first receipt
against the published calendar and records a separate event if the assessment changed.
New cases keep the first receipt instant in `filed_date` and the civil date in `filing_date`;
neither uses the clerk's acceptance time or a later resubmission. Date-only fields display consistently across viewer timezones. Search and docket
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
this action does not accept or reopen it, and a later resubmission keeps the ordered date. Legacy records keep missing receipt times missing.

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
date. A later corrected submission keeps that date: the order stays on the filing, and neither
the resubmission nor acceptance recomputes it.

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
changes. Five browser checks exercise the form, download fingerprints, acceptance,
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

`/notifications` provides paginated personal and court-scoped notice lists, email status
filters, exact filing-number lookup and private delivery history. A filing filter intersects
the recipient or assigned-court scope; it cannot expose another recipient's private inbox
or another court's notices. Unknown or inaccessible filings return an empty list. Search
starts at page one, and clearing the filing filter preserves the scope and email status.
Retry requests are serialized and logged with the operator's
reason. Queued events preserve the exact message; attempt events retain times and SMTP
response codes. SQLite and PostgreSQL triggers reject event updates and deletion. This
archive still requires production database privilege controls and protected backups.

Migration `a17d42b9c8e3` replaces the recipient-only index with
`(recipient_id, created_at, id)`, letting the newest-notice page avoid sorting an entire
inbox. A local PostgreSQL benchmark used 250,000 synthetic notices, a 50,000-notice inbox,
two warmups and seven measured executions of each actual list/count query:

| Query | Before median | After median |
| --- | ---: | ---: |
| Newest 25 recipient notices | 15.540 ms | 0.022 ms |
| Exact recipient notice count | 4.546 ms | 4.760 ms |

The sum of these query medians fell from 20.086 ms to 4.782 ms; this is database query
time, not measured API latency. Page-query shared buffer hits fell from 2,422 to 5. The
replacement adds about 8.14 MiB of index storage for this dataset; production write cost
and workload still need measurement. Exact counts remain available for status triage.
The existing filing index stays: an exact filing page already took about 0.23 ms, so a
second composite index was omitted. An interrupted concurrent-build regression verifies
upgrade recovery, downgrade and preservation of pending notices and retained messages.

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

**People and court access** provides a paginated identity directory, provisioning, identity-subject
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
staff. The browser
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
The browser now uses Keycloak's maintained adapter and keeps access, refresh and ID tokens
in memory. It removes legacy stored access tokens, restores private pages through SSO on
reload, and ends provider SSO on sign-out. The API client renews before dispatch, shares
concurrent renewal and discards responses from earlier accounts or local sessions. It never
replays a failed filing or payment request. Failed renewal preserves unsaved filing recovery;
explicit sign-out clears recovery from that tab and invalidates other portal tabs.

The local Keycloak 26.7.3 evaluation used rotating refresh tokens and a short access-token
lifetime. Browser checks covered concurrent renewal, an unchanged filing form, reload
recovery, multiple tabs, provider logout and a revoked session stopping Save draft before
any filing mutation reached the API. Access-token and refresh-token storage checks passed.
These checks do not establish production federation, MFA or session-policy readiness.
Provider-side revocation is observed on renewal; the API still validates each access token
and current account permissions. An IdP cookie alone does not authenticate API requests.

## Staff working across courts

The dashboard, filing review queue, fee review queue, case directory and court notices
share a working-court selection drawn from the signed-in account's verified assignments.
Clerk, judge and court administrator grants enable the workspace, independently of the
account's general type, including legacy grants. New appointments still require the
existing staff provisioning checks. Multiple roles at one court produce one choice. A remembered
court is used only while it remains assigned; no queue defaults to Wayne County.

The selected court persists across navigation and reload, including calendar links.
**Refresh assignments** reloads the profile without another sign-in. Revoked courts
disappear, and accounts with no staff assignments get an explicit empty state. Each API
request still checks the account's current authority for the actual record or court.
Changing the working court does not grant access or move a filing between courts.

Switching courts clears queue selections, pagination and pending reads. An open filing
review must be closed before switching; **Close review** discards its unsaved reason.
Selection remains disabled until an in-flight review action finishes. The dashboard
requests one envelope when it only needs the total pending count, and court screens
reuse the session's assignment lookup instead of fetching their own copies.

Browser verification used a production frontend build, actual API authorization and
RS256 tokens from an isolated synthetic issuer with demo authentication disabled. It
covered two staff courts, duplicate roles, a nonstaff grant, stale responses, a court
decision, revocation, an account with a different general type, persistence, notices,
sealed case records and desktop/mobile layouts. The synthetic 29-item queue response
was 25,015 bytes with 25 envelopes and 1,046 bytes with one; the total stayed 29. This
measures response size, not production latency or statewide load capacity.

## Court-managed participants and restricted-case access

**Court cases** lists public and sealed matters only for a staff member's assigned court,
with an exact case-number lookup and 25-record pages. The case docket links assigned staff
to **Manage case access**. Staff can record a party or counsel, identify a represented
party, link an existing account and explicitly grant restricted-case access. Generic
attorney roles accommodate representation that is not accurately described as plaintiff
or defendant. Retiring a record preserves it as former participation and removes its grant.

The same screen now records court-authorized instructions to restrict or restore public
case access. Restricting a case removes it from public search and unaffiliated favorites
and denies subsequent public docket/document requests. Court staff, explicit participant
grants and filers' access to their own envelopes remain governed by existing permissions.
Restoration requires an explicit confirmation and preserves individual document settings:
confidential documents remain restricted, while eligible accepted records become public
again. Staff must review the court's authority and existing publication settings before
restoring access. The control records an existing instruction; it does not adjudicate a
motion, issue a sealing order or implement document-specific exceptions. Use the separate
document publication controls for instructions limited to particular records. Courts must
validate those distinctions against applicable statutes, rules and orders; see the
[Michigan Judicial Institute's access guidance](https://www.courts.michigan.gov/4a5eab/siteassets/publications/benchbooks/civil/civilresponsivehtml5.zip/Civil/Ch_1_Trial_Court_Issues/Access_to_Court_Files_and_Records-.htm?rhtocid=_1_1_1).

Every public-access instruction requires a reason and authority reference. It commits the
restriction, shared access revision and private before/after audit together. An unchanged
instruction creates no audit entry or revision. Public-access changes and participant
edits share the existing `participant_version`, so either invalidates an older editor of
the other. No new table or migration is needed. The editor disables pending or uncertain
changes and requires a reload after a lost response or conflict. History includes both
types of access changes, loads only when requested and remains paginated. This removes
the history count and page queries from the initial participant screen. Case archives
include the case's current restriction and these retained case audit events.

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
Additional public-access checks cover search, docket, download and favorite visibility;
preserved confidential documents, original bytes and participant grants; concurrent access
and participant changes; authority revocation during a pending request; and rollback after
a deferred audit failure. Browser checks exercise uncertain-response recovery, confirmation
before restoration, conflicts and on-demand history loading with synthetic court records.
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
references; ordered envelope locks avoid reversed batch lock acquisition. The README's
[row-lock order](../README.md#row-lock-order) lists the order every path follows. Account and
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

## Portable case archives

The [case export command](CASE_EXPORT.md) produces a private ZIP package of a case's
linked records and exact stored bytes, including superseded documents and unpublished
copies. The database snapshot is read-only, and the recovery audit's retained-manifest
checks are reused. A missing file, inconsistent receipt or damaged delivery packet prevents
publication of a completed archive. Delivery checks compare the original source, selected
documents, contact/version fingerprint and frozen recipient/notification links, including
both cases touched by an inconsistent cross-case link. Later reviewed contact versions
and later submissions preserve historical packets. Recovery report format 2 includes
selection and contact-snapshot fingerprints for comparison with the pre-backup inventory;
it does not certify service or validate every portal/SMTP activity detail. Concurrent
exporters cannot overwrite each other's destination.

JSONL records preserve source identifiers and current metadata; the package also retains
the original transaction snapshots. Every binary source is verified while streaming in
64 KiB chunks. Identical contents share one archive object, and already compressed
document bytes are not recompressed. The manifest lists entry hashes, sizes and counts.
A recipient can verify the package without database access using the separately retained
manifest fingerprint. This supports records transfer and migration evaluation; court
approval, custody controls, source completeness, receiving-system mapping and restoration
remain separate requirements.

## Filing-list scale and detail loading

My filings and the clerk queue select summary columns and count only current attachments.
Removed documents and court-generated waiver/date orders are excluded from that count,
matching the full envelope. Attachment manifests, waiver explanations and filing-date
evidence load through the authorized detail endpoint when the user opens a filing.
The fee-review queue also selects only its displayed fields. Counts and pagination retain
their existing filer/court scope and deterministic ID ordering.

The clerk loads the current submission when a row is opened. Loading and failed reads
expose no decision buttons; retry, closing and switching rows cancel obsolete reads.
Opening a filing already decided by another reviewer disables intake decisions. A change
after details load still requires closing and reviewing the new submission after HTTP 409.

A local PostgreSQL 16 profile on 2026-09-06 used 50,000 synthetic filings across four courts
and 600,000 document records (nine current attachments per filing). The busiest test
filer owned 33,333 records. Each measurement used the real ASGI listing route and response
serialization, with authentication overridden to isolate listing work; two warm-up
requests were discarded and the next ten requests measured. These are local warm-cache
measurements, not deployment capacity targets.

| First page, 25 rows | Median before | Median after | Response bytes before → after |
| --- | ---: | ---: | ---: |
| My filings, all statuses | 27.92 ms | 6.79 ms | 121,629 → 35,282 |
| My filings, returned | 20.15 ms | 6.92 ms | 121,628 → 35,282 |
| Clerk queue, all pending | 12.00 ms | 8.20 ms | 120,759 → 34,993 |
| Clerk queue, submitted | 9.46 ms | 4.62 ms | 120,759 → 34,963 |
| Pending waivers | 11.82 ms | 6.16 ms | 141,518 → 34,948 |

Each of those list requests now performs three SELECTs rather than four and materializes
no filing/document ORM objects, previously 25 envelopes plus 225 documents. PostgreSQL
counts attachments for only the 25 returned filings. The replacement filer index removes
the 33,333-row sort and covers status counts; it replaces the single-column filer index.
That profile covers the summary projection and filer index changes. The fee-review response is unchanged in size;
its small measured latency difference (9.04 to 8.38 ms) is not treated as a performance win.

Status totals still grow with a filer's record count, and deep offset pages still require
skipping earlier matches. Concurrent filing activity can move records between pages.
Representative concurrent-user, cold-storage and deployment-network load testing remains
necessary before setting a court's capacity targets.

## Clerk queue search and waiting time

Assigned court staff can search `GET /api/v1/clerk/queue` by literal case title or linked
case number using `search` (maximum 200 characters). A value such as `#123` selects that
exact filing number. Searches retain the selected court, status and fee-waiver scope.
`waiting_48h_only=true` restricts results to receipts at least 48 elapsed hours old.

Each response includes `as_of`, `waiting_48h`, `oldest_submitted_at`, `submitted_count`
and `under_review_count`. These describe all matching records before pagination. Pending
waiver searches can include accepted filings. The browser uses the server's measurement
time for row ages, labels the interval directly and applies filters on explicit submission.
Elapsed age is separate from court deadline policy. Failed refreshes clear stale selections
and counts, and retry preserves the applied search. Opening a result fetches the current
authorized detail and focuses its review heading, including on small screens.

Migration `c72d9fa083b1` replaces the redundant court/status prefix index with a partial
index on court, receipt time, filing ID and status for submitted/under-review records.
The existing court/status/receipt index covers general status queries. PostgreSQL builds
the replacement concurrently, and reruns recover an invalid interrupted build. Upgrade,
downgrade and recovery tests preserve filing records, creation keys, queue ordering and
counts. SQLite uses an ordinary partial index.

A separate PostgreSQL 16 service profile on 2026-09-06 used 50,000 synthetic filings,
20,000 pending records and 600,000 document rows. The same vacuumed/analyzed dataset
served both implementations; each run discarded one warm-up and measured nine calls.
The 25-row queue page improved from 10.59 to 6.29 ms median. The old and new paths returned
the same IDs. These service timings exclude HTTP/authentication and deployment network costs.

The first combined implementation regressed because it sorted both pending statuses;
the replacement index removed that sort. Substring searches, exact counts and deep
offset pages still require representative load testing. Rendered verification exercised
searches, all-page counts, status/age filters, accepted pending waivers, an empty search,
refresh failure/retry and current-detail loading on desktop and mobile.

## Submit the filing that was reviewed

Full filing responses expose `submission_token`. Every `POST /filings/{id}/submit`
requires a JSON body containing `expected_submission_token` from the saved filing
shown at final review. Clients must update together with this API contract. List
summaries are not a substitute for loading and reviewing the full filing.

The API compares the token under the existing filing row lock after checking the
active owner's authority. It binds editable details, routing, status, submission
number, active document metadata/content hashes and the filing's fee state. A
mismatch returns 409 before creating a submission receipt or notification. Existing
idempotency keys recover their recorded submission before this comparison, even if
the court has since returned it. A new key cannot submit that returned filing with
an earlier review token. Existing byte-integrity, intake and fee checks still run.
No database migration, file reread or additional query is needed to derive the token.

Final review loads the current saved filing and validates it, offers authenticated
document downloads, and shows confidentiality labels. It replaces the stale duplicate
summary. Changed fee data or a submission conflict requires an explicit refresh and
review; the UI never refreshes the token and silently resubmits. Wizard navigation
waits for the submission response. Returned filings show the clerk's correction note
while being edited. A recovered submission shows its current status and receipt link.
When only a waiver is available, the fee form selects that available option.

API regressions cover missing review tokens, changed details, added/removed documents,
waiver changes, returned cycles and retry ownership. PostgreSQL contention tests hold
an editing lock through competing submission and verify that the old review cannot
create a receipt or notice. Production-auth browser checks use retained object-store
documents, court fee assessments and a published synthetic calendar; they cover
correction, retries, downloads, fee refresh, load failure, service-only recording and
mobile rendering. Court policy, real payment/CMS integration and deployed verification
remain separate readiness requirements.

## Bounded upload screening and scanner outages

Enabled ClamAV screening no longer falls back to heuristic acceptance after a daemon
error. The former `clamd` dependency, fail-open branch, unused content-type argument and
screening-disable switches are removed. A standard-library asynchronous INSTREAM client
uses one deadline across connection, transfer and verdict, bounded response size and
socket cleanup on success, failure or cancellation. Network waits do not occupy upload
worker threads. Detected threats/limit breaches return 422; incomplete screening returns
503 with a retry interval and leaves no stored document. Strict production startup requires
ClamAV, and Compose forwards the deadline without publishing the scanner's TCP port.

The supplied daemon config bounds scanning and retains the application's exact 100 MiB
upload boundary. Real ClamAV 1.4.6 returned a clean verdict for a compressed 110 MiB member
even with `AlertExceedsMax` enabled, consistent with [upstream issue 633](https://github.com/Cisco-Talos/clamav/issues/633).
An explicit container metadata signature now rejects members at or above the 101 MiB
per-file scan cap. The configuration and policy files use LF line endings so the same
checked-out files load on Windows Docker hosts. These controls supplement the scanner;
its verdict does not certify complete inspection of every possible embedded format.

A controlled latency experiment compared the previous and current scanner paths using
12 simultaneous 64 KiB inputs, two worker threads and a local daemon model with a fixed
150 ms response delay. With one warmup and five measurements per path, median batch time
fell from 974.41 ms to 169.63 ms. An unrelated worker task's median wait fell from 930.45 ms
to 0.41 ms. This models scanner latency and worker contention; it does not measure real antivirus
throughput or end-to-end request latency.
Actual-daemon checks separately cover clean data, the upload-size boundary, compressed
antivirus test data and archive-limit enforcement. API tests cover error/truncated/oversize
responses, timeouts, backpressure, cancellation and safe retries without stored artifacts.

## Recovering an uncertain document upload

Document and fee-waiver uploads carry a required UUID request key. The API binds it to
the file hash/size and upload metadata, and commits it with the document. A matching
retry returns that document without another scan, storage write, audit event or fee
revision. The same key with changed input returns a conflict. Removed documents cannot
be recreated by an old retry; successful uploads remain recoverable after submission
while enforcing current account and filing ownership checks.
Removal explicitly clears draft request links, including on SQLite where foreign-key
actions are disabled and document IDs can be reused.

The forms retain the key across an uncertain response, preserve the selected file and
explain how to retry. Uploads disable competing document edits and wizard navigation.
After a successful upload/removal, the document list is fetched from the server so it
also includes changes made in another tab. The shared upload helper returns the stored
document directly; its retained warnings no longer travel in a duplicate return value.

API regressions cover request mismatches, removed and submitted records, disabled
accounts and scanner outages. PostgreSQL tests exercise simultaneous identical and
conflicting uploads, visibility at HTTP response headers, and migration from a populated
prior schema. Browser checks deliberately discard successful responses for ordinary and
waiver uploads, verify exact byte counts and SHA-256 hashes, and recover one document
using the same key on desktop/mobile. Replays avoid the repeated screening and storage
work observed in the original duplicate-upload regression. Broader network/device load
and independent accessibility evaluation remain outstanding.

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
