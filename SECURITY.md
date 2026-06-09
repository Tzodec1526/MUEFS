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

- Set `ALLOW_DEMO_MODE=false`, `ALLOW_PUBLIC_REGISTRATION=false`.
- Replace every `change-me*` / `*_dev` secret (`SECRET_KEY`, Keycloak client secret, DB and
  MinIO credentials) with strong, externally-managed values.
- Configure Keycloak to require **verified email** before issuing tokens; provision
  privileged accounts (admin/clerk/judge) by binding their `keycloak_id` explicitly rather
  than relying on first-login auto-provisioning.
- Enable ClamAV (`MALWARE_SCAN_CLAMAV_ENABLED=true`) with `MALWARE_SCAN_FAIL_CLOSED=true`.
- Integrate a real payment processor and set `PAYMENTS_ARE_SIMULATED=false`.
- Serve over TLS, restrict `ALLOWED_ORIGINS`, and run the rate limiter against Redis.

## Reporting a vulnerability

This is a personal proof-of-concept. If you find a security issue, please open an issue
(without sensitive exploit details) or contact the maintainer privately via the repository
at <https://github.com/Tzodec1526/MUEFS>. Because the hosted demo is intentionally open as
described above, please scope reports to issues **beyond** the documented demo-mode
relaxations (for example: reading a sealed or confidential filing you should not be able
to, authentication bypass against the production code paths, injection, or storage escape).
