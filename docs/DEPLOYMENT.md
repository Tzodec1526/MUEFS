# Deployment Guide

This is the operational companion to [SECURITY.md](../SECURITY.md) — how to run MUEFS as a
real (non-demo) deployment. SECURITY.md explains *why* each setting matters; this document
explains *how* to configure it.

> The hosted demo (`render.yaml`, the root `Dockerfile`, `run_demo.py`) is intentionally
> open and single-instance. A production court deployment differs in the ways below.

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

## 3. TLS & reverse proxy

Terminate TLS at a reverse proxy (nginx, Caddy, or your platform's load balancer) in front
of the frontend and API. Forward `/` to the frontend and the API under its own path; set
`ALLOWED_ORIGINS` to the public origin. Never expose the API over plain HTTP in production.

## 4. Data & object storage

- **Database:** PostgreSQL (not the demo's SQLite). Back it up regularly (nightly `pg_dump`
  or your provider's managed snapshots) and test restores.
- **Object storage:** MinIO or S3 with scoped credentials. Enable bucket versioning and a
  backup/lifecycle policy for filed documents.

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

## 8. Container images

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
