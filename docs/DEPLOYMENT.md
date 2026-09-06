# Deployment Guide

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
MALWARE_SCAN_FAIL_CLOSED=true

# Bring up the scanner alongside the stack:
docker compose --profile security up -d
```

ClamAV downloads its signature database on first boot (a few minutes; it persists in the
`clamav_data` volume). `MALWARE_SCAN_FAIL_CLOSED=true` rejects uploads if the scanner is
unreachable.

## 6. Monitoring & operations

- **Health:** the API exposes `GET /health` for process liveness; the Compose backend
  already checks it. Verify database, object storage and other dependencies separately
  before routing filing traffic to a deployment.
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

## 8. Participant access migration

Migration `e83f2c91a6d4` preserves participant names, roles, account links and private contact
fields. It adds reviewed participation and explicit access grants. **Every legacy record
starts without a restricted-case grant**, because the old rows cannot distinguish a court
decision from a role inferred by filing acceptance. A per-case audit event records that
review is needed; the migration does not invent approval or delete the old records.

Before opening an upgraded portal to users, assigned court staff must review the affected
records through **Court Cases → Manage participants**, using the court's authorized source.
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
