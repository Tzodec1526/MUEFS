# Security Policy

MUEFS (Michigan Unified E-Filing System) is a **proof-of-concept demonstration**, not a
production court system. This document explains the project's security model: what is
deliberately open so the public demo is usable, what is protected regardless, and how a
real deployment would be hardened.

## Why demo mode is open

The hosted demo at `demo.tomcedoz.com` is meant to be explored by anyone (attorneys,
clerks, self-represented litigants, and the public) with **no sign-up and no real
identity provider**. To make that possible, the demo intentionally relaxes three things
that a production court deployment would never relax:

| Setting | Demo value | Why it's open in the demo | Production value |
| --- | --- | --- | --- |
| `ALLOW_DEMO_MODE` | `true` | Lets a visitor act as a seeded attorney/clerk/SRL/public user via an `X-Demo-User-Id` header instead of a Keycloak login, so the role-picker works without an IdP. | `false`: Keycloak Bearer JWT only. |
| `ALLOW_PUBLIC_REGISTRATION` | `true` in `run_demo.py` and Compose; off in the hosted demo | Enables `POST /api/v1/auth/register` for trying the API. The portal itself signs in as seeded roles. | `false`: identities come from the court IdP or an admin invite. |
| `PAYMENTS_ARE_SIMULATED` | `true` | No payment processor is integrated; the fee/waiver flow is demonstrated, not charged. | Integrate a PSP; never simulate. |

These are **configuration choices, not code defects**. The application code defaults to the
*secure* values (`allow_demo_mode=False`, `allow_public_registration=False`, `debug=False`); it is the
demo deployment artifacts (`.env.example`, `docker-compose.yml`) that turn them on. A court
running MUEFS would deploy with the production column above and get IdP-only authentication
with no self-registration.

> Because demo mode lets anyone obtain an account, **treat anything you can reach in the
> demo as public**. Do not upload real, sensitive, or privileged documents to the hosted
> demo.

## What stays protected even in the demo

Opening the *front door* (who can get an account) does **not** open the *rooms inside*.
The following controls are enforced server-side and are exercised by the test suite
regardless of demo mode:

- **Sealed and confidential matters.** Restricted docket access requires an explicit grant
  on an active participant record, a staff assignment at that court, or system administrator
  authority. Counsel grants require both the linked account and its matching verified bar
  number. A matching bar number or an accepted filing alone never grants access to the rest
  of a sealed case. Filers retain their own private envelopes, receipts and documents.
  Individually confidential documents remain restricted to the filer and assigned court
  staff. See `backend/app/services/access_service.py`.
- **Participant administration.** Only assigned staff may change a case's participant
  records, including for system administrators. Changes require a reason, recheck current
  authority and reject stale versions. Staff cannot edit their own linked participant
  record. Changes retain before/after values atomically in the audit log. Retiring one
  grant does not revoke a different active grant or court role. Migration `e83f2c91a6d4`
  preserves legacy records but disables inferred participant access until court review.
- **Public records, scoped.** Anonymous case search is limited to non-sealed cases. Public
  docket documents come from accepted filings and exclude restricted originals. An active
  reviewed copy exposes its own title, size and hash instead of the original's metadata.
- **Document publication.** Assigned staff prepare and inspect a separate PDF before
  explicitly publishing it with a reason and authority. Publication restricts the original;
  withdrawal removes the active public copy without restoring the original. Candidate
  metadata and earlier copies are retained with append-only database guards. Staff may
  inspect candidates; filers may read formerly published copies; public users may read
  only the current copy when case access permits. Fee-waiver records cannot be published
  through this workflow. Actor/filing/document locks recheck authority, versions reject
  stale changes, and audit/receipt failures roll back access changes. API responses use
  `private, no-store`; access changes apply to subsequent requests and cannot recall files
  already downloaded. Storage immutability and the completeness of a court's redactions
  require operational controls beyond these application checks.
- **Authentication.** Keycloak access tokens are validated with RS256 against the realm
  JWKS, with the issuer and expiry checked; the `none` algorithm is never accepted. OIDC
  auto-provisioning acts only on a **verified** email claim and refuses to auto-adopt a
  pre-existing privileged account (admin/clerk/judge or any bar-holding account).
- **Ownership / IDOR.** Filings, payments, favorites, notifications, and clerk review all
  enforce per-user ownership or court-role checks before returning or mutating data.
- **Administration.** System administrators explicitly bind identities and delegate court
  administration. Court delegates cannot change identity bindings or administrator grants.
  Stale edits are rejected and changes retain their operator, reason and before/after values.
  Deactivation and grant revocation affect subsequent protected requests even with an
  unexpired token. Bootstrap requires database operator access; see
  [the identity deployment procedure](docs/DEPLOYMENT.md#2-identity-keycloak).
- **Retained evidence.** Database triggers reject UPDATE and DELETE on audit logs, filing
  transactions, calendar revisions and email delivery events, including bulk SQL. Database
  owners can remove these controls; restrict runtime ownership, DDL and TRUNCATE privileges
  and maintain protected backups and the court's approved retention policy.
- **Upload safety.** Request bodies are capped before parsing (the 100 MB upload limit plus
  1 MiB for multipart forms, 1 MiB otherwise); uploads are restricted to an
  allowlisted set of document/image MIME types, stored under server-generated keys
  (path-traversal-guarded), and **malware-screened** (see below).
- **Stored-file integrity.** Submission, service-only recording and acceptance verify the
  actual SHA-256 and byte count of every current attachment using bounded reads off the
  event loop. Missing, altered or unavailable files block the transition without a new
  receipt or reviewer decision. Published copies and the verification endpoint check both
  values too. This checks bytes at the transition; private, versioned storage and protected
  backups must prevent or recover later changes. Upload PII warnings are retained advisory
  results, not exhaustive inspection or proof of redaction.
- **SQL injection / path traversal.** All database access is parameterized via SQLAlchemy;
  document storage paths are containment-checked.
- **Browser policy.** The served app's Content-Security-Policy sets `font-src 'self'`, because
  Public Sans is self-hosted. The app contacts no font host. `connect-src` adds only the
  configured Keycloak origin.

## Threat model & responsibility boundaries

MUEFS is a filing *front end* and workflow engine. It deliberately does **not** take over
identity, payments, or the court's official record. Those stay with established systems.

| Concern | Owned by | MUEFS's role |
| --- | --- | --- |
| User identity & credentials | The court's IdP (Keycloak / state SSO) | Validates IdP-issued RS256 JWTs; stores no passwords. |
| Payment / card data | The payment processor (PCI scope) | Records fee/waiver status only; no card data touches MUEFS (simulated in the demo). |
| System of record (official docket) | The court's existing CMS (JIS, Tyler Odyssey) | Without an integrated CMS adapter, acceptance is records-only and assigns MUEFS case numbers; a connected CMS stays authoritative. |
| Application authorization (who may read/file what) | **MUEFS** | Sealed/confidential access control, ownership/IDOR checks, audit logging. |
| Upload safety (type, size, malware, PII) | **MUEFS** | MIME allowlist, size cap, malware screening, MCR 1.109 PII warnings. |

In short, MUEFS owns *application-layer* security (authorization, upload safety, audit);
identity assurance, payment security, and the authoritative record remain with the court's
existing infrastructure.

## Upload malware screening

Every uploaded file is screened before it is stored (`backend/app/utils/malware_scan.py`),
on top of the MIME-type allowlist:

- A **built-in, offline heuristic scan** (always on, no external service) rejects native
  executables (Windows PE, ELF, Mach-O) and the EICAR antivirus test signature, even if a
  client spoofs the `Content-Type`. This is what keeps the public demo self-contained.
- An optional **ClamAV** backend (`MALWARE_SCAN_CLAMAV_ENABLED=true`, talking to a `clamd`
  daemon at `CLAMAV_HOST:CLAMAV_PORT` or `CLAMAV_SOCKET`) adds real signature-based
  detection for production. Once enabled, every upload requires a complete clean verdict.
  A timeout, disconnect, malformed reply or daemon error cannot fall back to heuristics.
  Startup refuses to run without ClamAV outside demo/debug mode, whether or not strict
  startup is enabled.

Detected threats return `422`; unavailable or incomplete screening returns `503` with
`Retry-After`. Neither result stores the document. `CLAMAV_TIMEOUT_SECONDS` bounds the
whole scanner exchange, including connection, transfer and verdict (default 30 seconds).
Cancellation closes the connection and discards buffered bytes. Scanner network waits do
not occupy the upload worker pool.

The supplied daemon configuration bounds scan work and enables limit alerts. An explicit
container metadata signature rejects members at or above the 101 MiB per-file scan limit,
including the highly compressed archive case that ClamAV's built-in limit alert can miss. Its TCP endpoint
is private to the Compose network; ClamAV's protocol has no application authentication.
The former `MALWARE_SCAN_ENABLED` and `MALWARE_SCAN_FAIL_CLOSED` switches are removed:
built-in screening always runs, and configured ClamAV screening always rejects failures.

## Hardening checklist for a real deployment

Configuration:

- Set `ALLOW_DEMO_MODE=false` and `ALLOW_PUBLIC_REGISTRATION=false`.
- Set `DEBUG=false`, `ENABLE_API_DOCS=false`, and `SECURITY_STRICT_STARTUP=true` for court deploys.
- When demo mode must stay on (public sandbox), set a strong `DEMO_MODE_SECRET` and serve it to
  the SPA via `/config.js` (hosted demo) or `VITE_DEMO_MODE_SECRET` at build time. The secret
  blocks casual `curl` impersonation of `X-Demo-User-Id`; it is not a substitute for IdP auth.
- Enable JWT audience verification (`JWT_VERIFY_AUDIENCE=true`, default outside DEBUG) and
  configure `JWT_AUDIENCES` if multiple Keycloak clients issue tokens.
- Set `STRICT_MIME_DETECTION=true` so uploads are rejected when libmagic cannot identify type.
- Set `TRUSTED_PROXY_IPS` to your load balancer's addresses or network (CIDR) so rate
  limits and audit records use the real client IP.
- Set `RATE_LIMIT_FAIL_CLOSED=true` when using Redis-backed rate limiting.
- Replace every demo secret (Keycloak administrator, database and object-storage
  credentials) with strong, externally-managed values. Generate them with:
  ```bash
  openssl rand -hex 32
  ```
- Configure Keycloak to require **verified email** before issuing tokens; provision
  privileged accounts (admin/clerk/judge) by binding their `keycloak_id` explicitly rather
  than relying on first-login auto-provisioning.
- Enable ClamAV (`MALWARE_SCAN_CLAMAV_ENABLED=true`) and verify its deadline, scan limits and current signatures.
- Integrate a real payment processor and set `PAYMENTS_ARE_SIMULATED=false`.
- Serve over TLS, restrict `ALLOWED_ORIGINS`, and run the rate limiter against Redis.

Scan before and after changes:

```bash
# Python dependency CVEs
pip install pip-audit && pip-audit

# Filesystem / image vulnerability + secret scan
trivy fs .
trivy image muefs-backend:latest

# Container image vulnerability summary
docker scout cves muefs-backend:latest

# Frontend dependency CVEs (production deps only)
npm --prefix frontend audit --omit=dev

# Docker daemon / host CIS benchmark
# https://github.com/docker/docker-bench-security
```

### Supported configurations

| | Demo (hosted / `run_demo.py`) | Recommended production |
| --- | --- | --- |
| Auth | Role-picker via `X-Demo-User-Id` + `X-Demo-Auth-Secret` (when `DEBUG=false`) | Keycloak (or state SSO) RS256 JWT only |
| Registration | Seeded roles; API self-registration when enabled | IdP / admin invite only |
| Database | SQLite | PostgreSQL |
| Object storage | Local filesystem | S3-compatible storage with restricted credentials |
| Malware scanning | Built-in heuristic | Built-in + ClamAV, fail-closed |
| Payments | Simulated | Real payment processor |
| Transport | HTTP (localhost) | TLS via reverse proxy |

## Reporting a vulnerability (responsible disclosure)

Please report security issues **privately**. Do not open a public issue with exploit details.

- **Preferred:** GitHub private vulnerability reporting. Open a draft advisory at
  <https://github.com/Tzodec1526/MUEFS/security/advisories/new>.
- **Email:** <tom@tomcedoz.com>.

Include the affected endpoint/file, a description, and reproduction steps. Because the hosted
demo is intentionally open as described above, please scope reports to issues **beyond** the
documented demo-mode relaxations. For example: reading a sealed or confidential filing you
should not be able to, an authentication bypass against the production code paths, injection,
or a storage escape. We aim to acknowledge reports within a few days.
