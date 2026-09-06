# Deployment Guide

Court intake management requires migration `f06c31a8b7d2`. It adds the intake revision and
public notice while preserving existing court and case-type availability. Apply it before
starting the updated API, and deploy the intake client with that API. Readiness requires
an exact schema revision match, so coordinate this rollout with routing and worker startup.
The migration can be downgraded while no intake publication exists; it refuses to discard
published revisions or notices. Recover an erroneous publication by publishing corrected
settings with a reason, preserving the history.

Authorized administrators use `/courts/{courtId}/intake` to close or reopen electronic
intake, restrict case types and publish filer instructions. Assign `CourtRole.ADMIN` only
to staff authorized to make those changes; `CourtRole.CLERK` alone is insufficient.
External clients use `GET` and `PUT /api/v1/courts/{courtId}/intake`, preserving the reviewed
`expected_version` and complete case-type list, plus a reason and authority reference.
History is restricted to the same administrators. After an uncertain response or HTTP 409,
read current settings and history before preparing another publication. Confirm the public
notice and available case types after each change, including reopening. Existing received
filings remain reviewable; calendars, filing-date orders and outage procedures are separate.

Document removal now requires migration `e95b20d7a6f1` and a supervised
`python -m app.storage_cleanup` process. Apply migrations before starting the updated API
and worker; Docker Compose includes `storage-worker`. Share the API's database and storage
configuration. The API commits removal immediately, while physical draft cleanup retries
storage outages in the worker. Monitor the pending queue and follow the
[storage lifecycle and recovery procedure](STORAGE_RECOVERY.md) for retention boundaries,
operator runs and backups.

This is the operational companion to [SECURITY.md](../SECURITY.md) — how to run MUEFS as a
real (non-demo) deployment. SECURITY.md explains *why* each setting matters; this document
explains *how* to configure it.

> The hosted demo (`render.yaml`, the root `Dockerfile`, `run_demo.py`) is intentionally
> open and single-instance. A production court deployment differs in the ways below.

Deploy the review client and API together. Single review requests now require
`expected_submission_count`; batch requests require a `filings` list containing each
`filing_id` and `expected_submission_count`. Older unversioned requests receive HTTP 422.
External clients must retain the submission number the reviewer saw and require a fresh
review after HTTP 409; retrying with a newly fetched number without review is unsafe.
See the [review request contract](STATE_READINESS.md#implemented-receipt-workflow).

Deploy the draft editor and API together as well. Changing a filing's title or description
now requires `expected_details_token` from the detail response's `details_token`.
Older detail-edit requests without this precondition receive HTTP 422; a conflicting
version receives 409 and requires comparison before another save. This change needs no
database migration. See [draft editing and recovery](STATE_READINESS.md#draft-editing-and-recovery)
for recovery scope and legacy browser entries.

New draft creation requires a UUID `Idempotency-Key` header on `POST /api/v1/filings`.
Deploy that client/API contract together after migration `b63c8e9204af`. Clients must keep
the same key and original creation fields after an uncertain response. A new filing returns
201; replay returns 200 with the current filing. A changed body returns 409 with the existing
owned `filing_id` for comparison, rather than replacing its contents. Missing or malformed
keys return 422. Keys are scoped to the filer and retained for the filing's lifetime.

The migration adds two nullable columns without backfilling legacy filings and builds a
partial unique index concurrently on PostgreSQL. Allow Alembic's autocommit block outside
any deployment-wide transaction; a rerun handles committed columns and an invalid interrupted
index. SQLite uses ordinary DDL. Downgrade is refused once creation keys exist, because
discarding them would allow previously completed requests to create duplicates.

Document uploads also require a UUID `Idempotency-Key` on
`POST /api/v1/filings/{id}/documents`. Deploy the API and both document/waiver upload forms
together after migration `d84a19f2c6b0`. Keep the same key, file bytes, filename, declared
content type, document type, title and confidentiality choice when retrying an uncertain
response. A matching completed request returns the original document without rescanning,
rewriting storage or changing fees again. Missing/malformed keys return 422; changed
requests and retries after document removal return 409. Refresh the saved filing before
starting another upload after a conflict. A completed request can be replayed after
submission, subject to current account and filing ownership checks.

The migration adds `document_upload_requests`; legacy documents remain unchanged. The
filing row lock serializes uploads and submission, and the request record commits with
the document before HTTP success. Removing a draft document clears its foreign-key link
while preserving the request key and fingerprint. Downgrade is refused once keys exist;
discarding them would allow completed uploads to be repeated.

Filing list responses now contain summaries with `document_count`, rather than full
envelopes and attachment arrays. This applies to `GET /api/v1/filings` and
`GET /api/v1/clerk/queue`, including pending waivers. Deploy their clients and API together;
clients opening a filing must fetch `GET /api/v1/filings/{id}` and keep the submission
number from that detail response for an individual review.

Migration `9d34e6a81c72` replaces the filer ID index with one supporting newest-first
listing and status counts. PostgreSQL builds the replacement concurrently before dropping
the old index; a rerun recovers an invalid interrupted build. Allow Alembic's autocommit
block to run outside any deployment-wide transaction. SQLite uses ordinary index DDL.
The migration changes no filing records and can be downgraded independently of earlier
retention migrations.

Migration `c72d9fa083b1` replaces the redundant court/status prefix index with a partial
index for pending filings in receipt/ID order. It uses the same concurrent-build and
interrupted-build recovery procedure on PostgreSQL; SQLite uses ordinary index DDL.
The queue API adds bounded `search` and `waiting_48h_only` filters, all-match age/status
counts and a server measurement time. Deploy the queue client with this API so its counts
and elapsed-age display use those fields. See [clerk queue search and waiting time](STATE_READINESS.md#clerk-queue-search-and-waiting-time).

## 1. Configuration & secrets

Copy `.env.example` to `.env` and change every demo value:

| Variable | Demo | Production |
| --- | --- | --- |
| `ALLOW_DEMO_MODE` | `true` | `false` |
| `ALLOW_PUBLIC_REGISTRATION` | `true` | `false` |
| `PAYMENTS_ARE_SIMULATED` | `true` | `false` |
| `DEBUG` | `true` | `false` |
| `SECRET_KEY` | `change-this-...` | `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` / `MINIO_ROOT_PASSWORD` / `S3_SECRET_KEY` | `*_dev` | strong, secrets-managed |
| `KEYCLOAK_CLIENT_SECRET` / `KEYCLOAK_ADMIN_PASSWORD` | demo | strong, secrets-managed |
| `ALLOWED_ORIGINS` | localhost | your real front-end origin(s) |
| `RATE_LIMIT_BACKEND` | `memory` / `redis` | `redis` |

Generate secrets with `openssl rand -hex 32` and store them in your platform's secret
manager — never in the repo.

`PAYMENTS_ARE_SIMULATED=false` disables the demo payment path. It does not connect a payment
processor; production payment requests remain unavailable until that integration exists.

## 2. Identity (Keycloak)

- Run production with Keycloak (or a state SSO) as the only auth path (`ALLOW_DEMO_MODE=false`).
- Require **verified email** before issuing tokens.
- Provision privileged accounts (admin/clerk/judge) by binding their `keycloak_id`
  explicitly; do not rely on first-login auto-provisioning for them.

Set `PROVISION_USER_ON_FIRST_OIDC_LOGIN=false` when the court requires every account to
be approved before access. Build the frontend with `VITE_ALLOW_DEMO_MODE=false` and the
same public `VITE_KEYCLOAK_URL` and `VITE_KEYCLOAK_REALM` as the API's `KEYCLOAK_URL` and
`KEYCLOAK_REALM`. Configure a public frontend client (`VITE_KEYCLOAK_CLIENT_ID`) with
authorization-code flow, PKCE S256, an exact HTTPS `/auth/callback` redirect, and the
portal's exact web origin. Do not put a client secret in the frontend.

Tokens must contain `sub`, `exp`, the configured issuer, and an API audience matching
`KEYCLOAK_CLIENT_ID` or `JWT_AUDIENCES`; set `JWT_VERIFY_AUDIENCE=true`. Configure the
frontend client's audience mapper to include the API. Keep Keycloak's `basic`, `profile`
and `email` client scopes: current Keycloak versions obtain the subject through the
`basic` scope. The local evaluation used Keycloak 26.7.3 with real browser PKCE and demo
authentication disabled; it does not validate a state federation or its production policy.
See [Keycloak's subject-mapper guidance](https://www.keycloak.org/docs/latest/upgrading/index.html).

The PostgreSQL search migration requires `pg_trgm` in the `public` schema. The migration
role needs database `CREATE` privilege to install it, or a database administrator must
preinstall it. See the search migration notes below for concurrent builds and recovery.

Apply migrations, then have an authorized database operator bind the first administrator
from `backend`, using the deployment's database configuration and the exact IdP subject:

```bash
alembic upgrade head
python -m app.admin_bootstrap --email administrator@example.gov --first-name Court --last-name Administrator --subject SUBJECT_FROM_IDP --reason "Initial appointment record ADMIN-001"
```

The command requires an unused email and subject and refuses to run while an active,
bound system administrator exists. It records an operator bootstrap event; it does not
create an IdP identity, password, verified email or court assignment. Protect database
operator access, including use of this command for recovery when no bound administrator
remains active.

Sign in and open **People & access** to provision further identities, including a second
system administrator for access changes and recovery. Only system administrators can
edit identity bindings, account types, active status and manually verified bar numbers,
or delegate court administration. Delegated administrators can grant and revoke clerk
and judge access within their courts; judicial grants require a provisioned judge account.
Use a court-approved source before marking a bar number verified: it can authorize access
to counsel's private case records.

Every change requires a reason or authority reference. Account type changes require
revoking existing staff assignments first. An administrator cannot change their own
system access or court grants. A stale form must be refreshed before saving. Deactivation
and revocation are checked by subsequent API requests. The court workspace's **Refresh
assignments** control reloads authorized court choices without signing out. A removed
selection falls back to a remaining staff court or displays the assignment-needed screen.
These operations do not revoke already downloaded
documents or cancel an operation that already passed authorization.

## 3. TLS & reverse proxy

Terminate TLS at a reverse proxy (nginx, Caddy, or your platform's load balancer) in front
of the frontend and API. Forward `/` to the frontend and the API under its own path; set
`ALLOWED_ORIGINS` to the public origin. Never expose the API over plain HTTP in production.

When FastAPI serves the SPA, its browser policy permits connections to the configured
Keycloak origin for PKCE token exchange. A separately hosted frontend must supply its own
Content-Security-Policy with the exact API and IdP origins in `connect-src`; keeping only
`'self'` blocks cross-origin sign-in. A stricter proxy policy can also block this flow, so
verify the deployed callback in a browser. See
[the browser connection policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/connect-src).

## 4. Data & object storage

- **Database:** PostgreSQL (not the demo's SQLite). Back it up regularly (nightly `pg_dump`
  or your provider's managed snapshots) and test restores.
- **Object storage:** MinIO or S3 with scoped credentials. Enable bucket versioning and a
  backup/lifecycle policy for filed documents.

The API requires FastAPI **0.121.1 or newer**. Its database dependencies explicitly use
`Depends(get_db, scope="function")`, including authentication, so the shared transaction
commits and releases its connection before response delivery. Keep that scope when adding
routes or overriding the dependency; the default request scope finalizes after the response.
See [FastAPI's dependency lifecycle](https://fastapi.tiangolo.com/advanced/advanced-dependencies/#dependencies-with-yield-and-scope).

A commit failure produces an error response rather than a provisional success. A timeout
or connection loss can still leave the client unsure whether a commit completed; reuse
the original submission `Idempotency-Key` and inspect its retained history when retrying.
This local database guarantee does not establish atomic delivery to a downstream CMS.

Downloads open storage after the authorization/audit transaction commits, read in 64 KiB
chunks, and close the stream on completion or disconnect. A slow client therefore does
not retain a database connection. The committed download audit records an authorized
access attempt; it does not prove that the client received every byte.

Use the [storage recovery audit](STORAGE_RECOVERY.md) on a quiescent restored database and
matching objects. It checks archived originals, private decisions, all prepared public
copies and retained transaction fingerprints with read-only credentials. Require a complete
report, resolve discrepancies, and compare its inventory with the backup source before
declaring recovery successful. It does not repair records or remove objects.

## 5. Malware scanning (ClamAV)

The built-in heuristic scan is always on. For production, also enable ClamAV:

```bash
# In .env:
MALWARE_SCAN_CLAMAV_ENABLED=true
CLAMAV_TIMEOUT_SECONDS=30

# Bring up the scanner alongside the stack:
docker compose --profile security up -d
```

ClamAV downloads its signature database on first boot (a few minutes; it persists in the
`clamav_data` volume). Once enabled, ClamAV failures always reject the upload with a
retryable `503`; there is no fallback to heuristics. The deadline covers connection,
transfer and response. Detected threats return `422`. Strict startup requires the scanner
outside demo/debug mode. Retire the obsolete `MALWARE_SCAN_ENABLED` and
`MALWARE_SCAN_FAIL_CLOSED` environment variables.

The scanner's TCP port stays inside the Compose network. The mounted
[`clamd.conf`](../clamav/clamd.conf) sets a 100 MiB stream limit, a 101 MiB per-file scan
limit (including the application's exact 100 MiB boundary), a 400 MiB aggregate scan
limit and a 25-second engine limit. PCRE matching uses the same per-file cap.
`AlertExceedsMax` enables engine limit detections. The mounted
[`muefs-limits.cdb`](../clamav/muefs-limits.cdb) additionally rejects container members at or
above 101 MiB: the real-daemon regression reproduced the highly compressed archive gap
reported in [ClamAV issue 633](https://github.com/Cisco-Talos/clamav/issues/633), even with
`AlertExceedsMax` enabled. Keep this policy file mounted alongside the official databases. Its mount must allow writes
because the official image changes database-file ownership at startup; the configuration
mount stays read-only. Keep these limits aligned with `MAX_FILE_SIZE_MB` when changing upload policy;
load-test time and memory with the court's actual documents. Do not disable limit alerts
to turn an incomplete scan into a clean verdict.

Verify clean uploads, a harmless antivirus test file, scanner downtime and recovery before
accepting filings. Monitor daemon health, signature freshness, scan-limit detections and
`503` rates separately from API liveness. Maintain supported ClamAV patches and signature
updates. The client protocol follows the [ClamAV INSTREAM specification](https://docs.clamav.net/manual/Usage/ClamdProtocol.html).

## 6. Monitoring & operations

- **Liveness:** `GET /health` checks only whether the API process can respond. Use it for
  process restart decisions; a database outage does not make this endpoint fail.
- **Database readiness:** `GET /ready` returns 200 only when the API can obtain a database
  connection and its recorded Alembic revisions exactly match the migrations bundled with
  this build. Missing, older or unknown revisions return 503 `schema_mismatch`. Connection
  failures return `database_unavailable`; the three-second budget covers pool acquisition,
  queries and connection release, with `database_timeout` on expiry. Responses are uncached,
  and 503 responses include `Retry-After: 5`. They expose no connection details. The probe
  performs metadata reads; it never applies migrations or repairs the database.
  Compose and Render use `/ready`; configure production traffic routing to require it too.
  Exact revision matching requires a coordinated release: applying a migration also makes
  older API builds fail readiness. Plan traffic routing or a maintenance window accordingly,
  and apply migrations before directing filing traffic to the new build. A recorded migration
  revision is not a full schema-integrity or restore audit. Monitor object storage, identity,
  Redis, scanners and workers separately; this endpoint does not test their availability or
  establish overall filing readiness.
  Hosted-demo checks read the existing seed template through a read-only SQLite connection.
  Health and readiness probes create no visitor cookie or sandbox, and a missing template
  fails the check without being recreated. Individual visitor databases are not probed.
- **Audit log:** filing and access actions are recorded server-side; export them to your
  SIEM / log store for retention.

Migration `d26e49b73c18` adds identity change versions, retained administration history and
unique court grants. It archives redundant historical grant identifiers before removing
duplicate assignments. SQLite and PostgreSQL triggers reject UPDATE and DELETE on the
audit log, filing transactions, court calendars and email delivery events. Use a restricted
runtime database role without ownership, DDL or TRUNCATE privileges; table owners can
remove triggers. Protect and restore-test backups independently of these guards. The
migration refuses an automatic downgrade that would discard the retained evidence.
- **Rate limiting:** run against Redis (`RATE_LIMIT_BACKEND=redis`).

## 7. Filing notice email

Email is disabled by default. Configure the API and the separate notice worker with the
same database, sender and public portal origin:

```dotenv
EMAIL_DELIVERY_ENABLED=true
PORTAL_BASE_URL=https://filing.example.gov
SMTP_HOST=your-approved-relay
SMTP_PORT=587
SMTP_TLS=starttls
SMTP_FROM=notices@your-approved-domain
SMTP_USERNAME=your-relay-account
SMTP_PASSWORD=provided-through-your-secret-manager
```

Use `SMTP_TLS=ssl` with port 465 when the approved relay requires implicit TLS. TLS
certificates and hostnames are verified. SMTP credentials are optional for a relay that
authenticates the deployment by another approved method. Plain SMTP is restricted to a
loopback mail sink with `DEBUG=true`; demo mode cannot use an external relay.

Run migrations before enabling mail, then supervise the sender independently of the API:

```bash
alembic upgrade head
python -m app.notification_worker
```

For the Compose stack, the optional worker is available through
`docker compose --profile email up -d --build notice-worker` after configuration and
migration. It shares mail settings with the API. For a bounded operations run, use
`python -m app.notification_worker --once`; this drains only messages currently due.

Monitor the process and the oldest pending notice. A stopped worker leaves queued
messages in PostgreSQL. A started attempt without a result is marked unknown after ten
minutes once a worker runs recovery; court staff inspect the relay records and decide
whether to retry from **Notices**. Confirmed temporary failures retry up to five attempts.
Keep the relay's logs available for that investigation. SMTP acceptance alone does not
prove inbox delivery or legal service. Configure bounce handling, sender-domain
authentication and operational alerts with the selected provider before a court pilot.

Only verified account addresses receive email. Require the IdP's matching `email` and
`email_verified` claims on authentication. Generic alerts link to protected filing history;
the email does not attach court documents or expose case details. Existing pending notices
remain portal-only when upgrading; no backlog is sent automatically.

Staff can investigate a receipt's filing number from **Notices** while keeping the selected
court and email status. `GET /api/v1/notifications?filing_id=123` applies the exact filing filter
inside the existing recipient scope, or the assigned court scope when `court_id` is also
provided. The same filters apply to the total and every page.

Apply migration `a17d42b9c8e3` before deploying this API version. It replaces the notice
recipient index with `(recipient_id, created_at, id)`. PostgreSQL builds the replacement
concurrently and keeps the old index until the replacement is ready. Run Alembic through
its normal connection, without an enclosing application transaction. If a build is
interrupted, resolve the cause and rerun the upgrade; it removes an invalid partial index
before rebuilding. A downgrade restores the old index and leaves notices unchanged.
Budget disk space for both indexes during the build. See the measured read improvement
and storage tradeoff in [State readiness](STATE_READINESS.md#filing-notice-email).

## 8. Participant access migration

Migration `e83f2c91a6d4` preserves participant names, roles, account links and private contact
fields. It adds reviewed participation and explicit access grants. **Every legacy record
starts without a restricted-case grant**, because the old rows cannot distinguish a court
decision from a role inferred by filing acceptance. A per-case audit event records that
review is needed; the migration does not invent approval or delete the old records.

Before opening an upgraded portal to users, assigned court staff must review the affected
records through **Court Cases → Manage case access**, using the court's authorized source.
Record the reason/reference, correct the role, link the intended existing account and
explicitly grant access where authorized. Counsel grants also require a matching verified
bar number. Ambiguous case-insensitive email matches must be resolved by identity
administration before linking; the app never chooses between those accounts automatically.

Test a grant and retirement using separate staff and filer accounts. Confirm that retired
grants no longer open a sealed docket, while the filer can still read their own envelopes
and receipts. Check for other active participant grants and court assignments when reviewing
someone's remaining access. History is retained; automatic downgrade is refused.

This rollout requires court approval of the access policy and record review. Participant
records do not replace CMS appearance data, court orders governing access, withdrawal
procedures, or electronic-service enrollment.

Public case access instructions use the same screen and existing `participant_version`;
this addition needs no new migration. Deploy the client and API together. Assigned clerks,
judges and administrators can record a restriction or restoration with a reason and
authority reference. A system administrator needs an assignment at this court too.
External clients use `PUT /api/v1/cases/{caseId}/public-access` with `expected_version`,
`is_sealed`, `reason` and `authority_reference`; restoration also requires
`confirm_public_release: true`. The legacy `is_sealed` field controls portal visibility.
The participant history endpoint now includes `case.public_access_changed` events.

Validate the court's authority and record-level exceptions before changing case-wide
access. A restriction hides public search/docket/download access on subsequent requests;
it does not recall prior downloads or revoke independent staff, participant or filer
access. Restoration exposes eligible records according to their existing document
settings. Verify public and restricted documents with separate accounts after each change.
On HTTP 409 or an uncertain response, reload the records and inspect history before a new
instruction. Public-access and participant edits invalidate each other's older versions.

## 9. Container images

The root `Dockerfile` builds the hosted demo, including `app.demo.server` and isolated
SQLite sessions. A court deployment must run `app.main:app` against its PostgreSQL database,
disable demo mode and isolated sessions, and serve the built frontend with its production
configuration. Supervise the notice worker as a separate process. Pin base images to a
digest in the production build pipeline; `render.yaml` is a demo deployment example.

## Pre-launch checklist

- [ ] `ALLOW_DEMO_MODE=false`, `ALLOW_PUBLIC_REGISTRATION=false`, `PAYMENTS_ARE_SIMULATED=false`, `DEBUG=false`
- [ ] All `change-me*` / `*_dev` secrets replaced
- [ ] Keycloak email verification enforced; privileged accounts bound explicitly
- [ ] TLS terminated; `ALLOWED_ORIGINS` locked to real origins
- [ ] PostgreSQL + object-storage backups configured and a restore tested
- [ ] ClamAV enabled and fail-closed
- [ ] Health checks and audit-log export wired up
- [ ] `pip-audit`, `trivy fs .`, and `npm --prefix frontend audit --omit=dev` reviewed

## 10. Reviewed public-copy rollout

Run migration `f94c81e2b7d5` before enabling the new document access screen. It creates
retained copy records and a versioned active-copy pointer without modifying original files,
titles or receipts. Existing documents keep their current visibility. The database rejects
updates/deletes of copy metadata; automatic downgrade is refused to preserve evidence.

Authorize the court's classification and release policy before staff use **Manage public
access**. Verify preparation with a safe synthetic PDF, inspect the downloaded candidate,
publish with a reason/authority and check its docket/download as an anonymous user. Confirm
that the original is now restricted, then withhold the copy and confirm both public URLs
are denied. Check that the filer can still retrieve the original and prior published copy,
that unassigned staff cannot change access, and that the retained history records each
operator and decision. Review hidden text, annotations and metadata using approved tools;
the five-page sampled PII scan is advisory and performs no redaction.

Keep originals and every prepared copy in private storage. Back up and restore the database
and objects together, validate hashes and configure storage permissions/versioning for the
court's retention policy. A database append-only trigger does not make object storage
immutable. A failed request cleans up a newly uploaded candidate when it can, but a process
crash or commit failure can leave an unreferenced private object. Reconcile these objects
under an approved retention procedure; never infer permission to delete a referenced copy.
Preserve `private, no-store` on API responses through any proxy/CDN. Withdrawal controls
subsequent downloads; files already downloaded cannot be recalled.

## 11. Stored-file integrity and retained screening

Run migration `a71b03d9e6f2` before this application version. It adds nullable upload PII
warnings to document records. Existing documents keep `NULL`, meaning no screening result
was retained; an empty list means the sampled upload check recorded no warnings. The
migration does not reread files or invent historical scans, hashes or receipts. Automatic
downgrade is refused because it would discard retained results.

Submission and acceptance now stream each current attachment and compare both SHA-256 and
actual byte count with its record. A missing file, storage error or mismatch returns HTTP
409 and leaves the filing and transaction history unchanged. Rejection and return remain
available. The clerk's review panel retains the document-specific error. A completed
idempotent submission retry replays its existing result without another storage pass.

Before rollout, reconcile referenced files against a restored copy of the database and
object store. Investigate mismatches; do not update hashes merely to make verification
pass. Restore retained files from approved backups. Draft files can be removed and uploaded
again through the normal correction workflow. Older demo seeds with invented file keys
require a fresh disposable demo database to obtain the new, marked sample PDFs; production
and retained evaluation records must not be reset to solve storage failures.

Measure the added storage-read cost with representative document sizes and the deployed
object store. Advisory validation performs no document reads, while submission/acceptance
read all current attachments in 64 KiB chunks off the event loop. Keep storage private,
apply the court's retention/versioning policy and exercise recovery. A successful integrity
check cannot prevent an out-of-band object replacement after the check.

## 12. Public case search indexes

Migration `d4e7a12b93f0` replaces the single-column case-number and party-name B-tree
indexes with PostgreSQL GIN trigram indexes for the application's literal substring
searches. The unique `(court_id, case_number)` constraint remains. SQLite drops the
unused indexes and keeps the same search behavior without a PostgreSQL extension.

Install `pg_trgm` in `public` before upgrading if the migration role lacks database
`CREATE` privilege. The migration installs the extension when permitted and refuses to
move an existing installation from another schema. Resolve that prerequisite with the
database administrator before rollout. PostgreSQL documents the extension's
[installation privileges and LIKE/ILIKE support](https://www.postgresql.org/docs/16/pgtrgm.html).

Run `alembic upgrade head` through the normal migration connection. Indexes build
concurrently so filing writes can continue, although the build consumes CPU, I/O and
disk and can wait for existing transactions. Alembic now commits each migration
separately; the concurrent index operations also commit individually. Do not wrap the
upgrade in an external transaction. If a build fails or is interrupted, resolve its
cause and rerun the upgrade. It retains valid completed indexes and replaces invalid
partial builds before removing the old indexes. Downgrading this revision rebuilds the
old indexes and leaves the shared extension installed. See
[PostgreSQL concurrent index recovery](https://www.postgresql.org/docs/16/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY)
and [Alembic autocommit transactions](https://alembic.sqlalchemy.org/en/latest/api/runtime.html#alembic.runtime.migration.MigrationContext.autocommit_block).

Substring searches use transaction-local custom plans: a rare surname and a name
matching most records need different access paths. This prevents a cached generic plan
from slowing broad searches after selective ones; the setting resets when the request
transaction ends. Court metadata is fetched once for the displayed results, and search
does not load participant email, telephone, address or account IDs. Broad and very short
terms can still require substantial scanning. Measure the deployed workload, index size,
write overhead and query plans; the synthetic measurements in `STATE_READINESS.md` are
not a statewide capacity test.

See [PostgreSQL's prepared-plan selection](https://www.postgresql.org/docs/16/sql-prepare.html)
for the distinction between generic and parameter-specific plans.

## 13. Filing intake and destination validation

The API enforces `courts.is_efiling_enabled` and `case_types.is_active` for new drafts
and submissions. Treat changes to these flags as intake changes, with a court-approved
process and filing alternatives communicated to users. An in-flight PostgreSQL
submission holds shared locks until its receipt commits; a concurrent configuration
change waits, then applies to subsequent attempts. Previously committed receipts remain
available and idempotent retries remain valid. Closing intake does not block staff from
finishing valid filings already received.

Clients opening a new case must send `filing_type: "initial"` without a `case_id`.
The default `subsequent` type requires a case; service-only records also require a case.
Unknown types and inconsistent new-case/existing-case combinations return HTTP 422.
Court, case-type and case relationships are checked independently of frontend selections.
Saved-record displays may use `GET /api/v1/courts/{id}/case-types?include_inactive=true`
to resolve disabled type labels; this does not enable filing into those types.

No data migration is needed for these controls, and existing records are not rewritten.
Reconcile incorrect legacy court/case/type assignments before acceptance. A rejected
acceptance attempt sends nothing to the CMS, while return/rejection and unaffected batch
items remain available. An inconsistent draft must be replaced with a correctly addressed
draft or resolved through a court-approved correction process; preserve its documents
and any earlier receipts. Exercise these paths with representative imported records
before rollout.

## 14. Court service instructions

Run `alembic upgrade head` before deploying the service-instruction API. Migration
`a63b29d5e104` adds reviewed participant links, authority and versioning to the existing
contact table. Schedule the schema change with normal database migration controls.
Legacy contact rows remain intact, inactive and unlinked. Reconcile them against court
records before entering current instructions; no address is automatically enrolled.

Assigned staff use **Case participants → Service instructions**. Establish procedures
for reviewing registrations, exemptions, agreements, recipient identity and changes.
The current workflow supports one primary destination per participant. Service contacts
and their before/after history are included in private case archives; access and retention
controls must cover those addresses and source references.

Editing service instructions sends no documents or invitations. The legacy `served`
filing status means service-only documents were recorded; it does not establish service.

## 15. Selected document delivery

Migration `f7a21b84d903` adds append-only delivery packages, recipient snapshots and
portal events. Retained evidence cannot be automatically downgraded. Apply migrations
before running the updated API or worker, and include these tables in protected backups.

After the court evaluates its enrollment, service authority, restricted-document policy
and relay operations, explicitly set `SERVICE_DELIVERY_ENABLED=true` in both the API
and existing notice worker. This also requires `EMAIL_DELIVERY_ENABLED=true` and the
SMTP/portal configuration in section 7. Compose shares both flags between those services.
The separate flag defaults to false; ordinary filing alerts do not enable document delivery.

The filer or assigned staff opens **Filing history → Document deliveries → Select documents
& recipients**. The sender must have a verified account and, for ordinary filers, current
court-reviewed case participation. This workflow accepts subsequent, motion and service-only
documents with a retained current receipt on an existing case. Case-initiating service uses
the applicable procedure outside this workflow. Each request requires explicit contents,
recipients, confirmation and a UUID `Idempotency-Key`; retries of the same key and selections
return the same package. A changed receipt or contact version requires review again.

Packages retain selected document manifests and each recipient's reviewed instructions.
Fee-waiver material is excluded. Other confidential documents require the sender's explicit
selection and review of recipient authority. Email contains a generic alert and a protected
link to that recipient's package. It grants access only to selected documents, not the
sender's full submission. Downloads recheck current participation/access and verify stored
bytes against the retained hash and size before streaming. Large files spill to temporary
disk after 8 MiB; provision and protect the API host's temporary storage accordingly.

The existing outbox checks frozen instructions again when claiming an alert. Changed
instructions block that alert instead of silently changing its destination. Confirmed
temporary SMTP errors use the existing bounded retries. A failed alert can be retried from
its delivery record by the sender or assigned staff with a reason; uncertain outcomes
require staff review. Generic notification retries cannot bypass these controls. Disabling
the service flag blocks unclaimed service alerts; an already claimed SMTP attempt may finish.
Previously recorded packages remain accessible to authorized viewers.

The delivery inbox and linked notices let recipients download and explicitly acknowledge
a package. Download requests, acknowledgments and SMTP results are separate retained events,
included in private case archives. Email-address changes do not retarget past packages;
loss of case participation or required access prevents recipient downloads. Relay acceptance
and download requests do not prove inbox receipt, transfer completion or legally sufficient
service. This release does not ingest bounces, record postal service evidence, certify proof
of service, or calculate remedies/deadlines. Establish those procedures and validate the
deployed configuration before a court pilot. Use only a loopback mail sink for synthetic tests.

### Court-reviewed delivery-failure reports

Assigned staff can open a delivery record and select **Record a delivery-failure report**
after a completed or uncertain transmission. Record the relay notice or recipient report,
its source reference, observation time and description, and review it against the displayed
recipient, Message-ID and attempt. The application retains that court observation in the
delivery history and alerts the sender through the existing notices/outbox flow. Keep the
underlying source evidence under the court's records policy; this form does not ingest or
authenticate a provider webhook or a delivery-status message.

The new `failure_reported` status distinguishes a reviewed report from an SMTP exchange.
It preserves the original message, relay acceptance time and recipient acknowledgment.
It schedules no automatic retry. Only assigned staff can request another alert after
reviewing that report, and current frozen contact checks still apply. A new attempt
invalidates an old review form; replaying the same report key returns its original record
without replacing a newer retry or sending a duplicate attention notice. Concurrent
reviewers and late SMTP results cannot overwrite the newer state. Reports and linked
sender notifications are included in private case archives.

Deploy the updated API and notice worker together: older application versions do not
recognize `failure_reported`. The existing text-backed delivery-status column and retained
event tables support this change without another database migration. A report records a
court-reviewed observation; it does not adjudicate service, extend a deadline or establish
that an alternative service method has been completed.
