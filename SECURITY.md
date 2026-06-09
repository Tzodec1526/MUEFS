# Security Policy

MUEFS (Michigan Unified E-Filing System) is a **proof-of-concept demonstration**, not a
production court system. This document explains the project's security model: what is
deliberately open so the public demo is usable, what is protected regardless, and how a
real deployment would be hardened.

## Why demo mode is open

The hosted demo at `demo.tomcedoz.com` is meant to be explored by anyone — attorneys,
clerks, self-represented litigants, and the public — with **no sign-up and no real
identity provider**. To make that possible, the demo intentionally relaxes three things
that a production court deployment would never relax:

| Setting | Demo value | Why it's open in the demo | Production value |
| --- | --- | --- | --- |
| `ALLOW_DEMO_MODE` | `true` | Lets a visitor act as a seeded attorney/clerk/SRL/public user via an `X-Demo-User-Id` header instead of a Keycloak login, so the role-picker works without an IdP. | `false` — Keycloak Bearer JWT only. |
| `ALLOW_PUBLIC_REGISTRATION` | `true` | Lets visitors self-register to try the filing flow. | `false` — identities come from the court IdP or an admin invite. |
| `PAYMENTS_ARE_SIMULATED` | `true` | No payment processor is integrated; the fee/waiver flow is demonstrated, not charged. | Integrate a PSP; never simulate. |

These are **configuration choices, not code defects**. The application code defaults to the
*secure* values (`allow_demo_mode=False`, `allow_public_registration=False`); it is the
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

- **Sealed and confidential matters.** Sealed dockets and their filings are restricted to
  the parties (accounts linked to the case), counsel of record, the filer, court staff for
  that court, and system admins. Anonymous visitors never reach sealed matters. Counsel of
  record is matched either by account linkage (`user_id`) or by a **verified** bar number —
  a self-asserted bar number entered at registration is *not* trusted and cannot be used to
  read another attorney's sealed cases. Documents individually marked confidential are
  further restricted to the filer and court staff. See `backend/app/services/access_service.py`.
- **Public records, scoped.** Anonymous case search and docket viewing are limited to
  non-sealed cases and non-confidential, non-draft filings.
- **Authentication.** Keycloak access tokens are validated with RS256 against the realm
  JWKS, with the issuer and expiry checked; the `none` algorithm is never accepted. OIDC
  auto-provisioning acts only on a **verified** email claim and refuses to auto-adopt a
  pre-existing privileged account (admin/clerk/judge or any bar-holding account).
- **Ownership / IDOR.** Filings, payments, favorites, notifications, and clerk review all
  enforce per-user ownership or court-role checks before returning or mutating data.
- **Upload safety.** Uploads are size-limited (streamed, 100 MB), restricted to an
  allowlisted set of document/image MIME types, stored under server-generated keys
  (path-traversal-guarded), and **malware-screened** (see below).
- **SQL injection / path traversal.** All database access is parameterized via SQLAlchemy;
  document storage paths are containment-checked.

## Threat model & responsibility boundaries

MUEFS is a filing *front end* and workflow engine. It deliberately does **not** take over
identity, payments, or the court's official record — those stay with established systems,
which is what keeps adoption low-risk and avoids vendor lock-in.

| Concern | Owned by | MUEFS's role |
| --- | --- | --- |
| User identity & credentials | The court's IdP (Keycloak / state SSO) | Validates IdP-issued RS256 JWTs; stores no passwords. |
| Payment / card data | The payment processor (PCI scope) | Records fee/waiver status only; no card data touches MUEFS (simulated in the demo). |
| System of record (official docket) | The court's existing CMS (JIS, Tyler Odyssey) | Pushes accepted filings via the adapter layer; the CMS stays authoritative. |
| Application authorization (who may read/file what) | **MUEFS** | Sealed/confidential access control, ownership/IDOR checks, audit logging. |
| Upload safety (type, size, malware, PII) | **MUEFS** | MIME allowlist, size cap, malware screening, MCR 1.109 PII warnings. |

In short, MUEFS owns *application-layer* security (authorization, upload safety, audit);
identity assurance, payment security, and the authoritative record remain with the court's
existing infrastructure.

## Upload malware screening

Every uploaded file is screened before it is stored (`backend/app/utils/malware_scan.py`),
on top of the MIME-type allowlist:

- A **built-in, offline heuristic scan** (always on, no external service) rejects native
  executables (Windows PE, ELF, Mach-O) and the EICAR antivirus test signature — even if a
  client spoofs the `Content-Type`. This is what keeps the public demo self-contained.
- An optional **ClamAV** backend (`MALWARE_SCAN_CLAMAV_ENABLED=true`, talking to a `clamd`
  daemon at `CLAMAV_HOST:CLAMAV_PORT` or `CLAMAV_SOCKET`) adds real signature-based
  detection for production. Set `MALWARE_SCAN_FAIL_CLOSED=true` to reject uploads when the
  scanner is enabled but unreachable.

A rejected upload returns `422 Unprocessable Entity` and is never persisted.

## Hardening checklist for a real deployment

Configuration:

- Set `ALLOW_DEMO_MODE=false` and `ALLOW_PUBLIC_REGISTRATION=false`.
- Replace every `change-me*` / `*_dev` secret (`SECRET_KEY`, Keycloak client secret, DB and
  MinIO credentials) with strong, externally-managed values. Generate them with:
  ```bash
  openssl rand -hex 32
  ```
- Configure Keycloak to require **verified email** before issuing tokens; provision
  privileged accounts (admin/clerk/judge) by binding their `keycloak_id` explicitly rather
  than relying on first-login auto-provisioning.
- Enable ClamAV (`MALWARE_SCAN_CLAMAV_ENABLED=true`) with `MALWARE_SCAN_FAIL_CLOSED=true`.
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
| Auth | Role-picker via `X-Demo-User-Id` | Keycloak (or state SSO) RS256 JWT only |
| Registration | Open self-registration | IdP / admin invite only |
| Database | SQLite | PostgreSQL |
| Object storage | Local filesystem | MinIO / S3 with restricted credentials |
| Malware scanning | Built-in heuristic | Built-in + ClamAV, fail-closed |
| Payments | Simulated | Real payment processor |
| Transport | HTTP (localhost) | TLS via reverse proxy |

## Reporting a vulnerability (responsible disclosure)

Please report security issues **privately** — do not open a public issue with exploit details.

- **Preferred:** GitHub private vulnerability reporting — open a draft advisory at
  <https://github.com/Tzodec1526/MUEFS/security/advisories/new>.
- **Email:** <tom@tomcedoz.com>.

Include the affected endpoint/file, a description, and reproduction steps. Because the hosted
demo is intentionally open as described above, please scope reports to issues **beyond** the
documented demo-mode relaxations — for example: reading a sealed or confidential filing you
should not be able to, an authentication bypass against the production code paths, injection,
or a storage escape. We aim to acknowledge reports within a few days.
