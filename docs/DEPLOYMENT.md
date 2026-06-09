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

- **Health:** the API exposes `GET /health`; wire it to your platform's liveness/readiness
  checks (the `docker-compose.yml` backend service and the production `Dockerfile` already do).
- **Audit log:** filing and access actions are recorded server-side; export them to your
  SIEM / log store for retention.
- **Rate limiting:** run against Redis (`RATE_LIMIT_BACKEND=redis`).

## 7. Container images

The production root `Dockerfile` builds the SPA + API into one image, runs as a non-root user
(`appuser`), and ships a `HEALTHCHECK`. For full reproducibility, pin base images to a digest
in your build pipeline. See `render.yaml` for a worked single-instance deployment.

## Pre-launch checklist

- [ ] `ALLOW_DEMO_MODE=false`, `ALLOW_PUBLIC_REGISTRATION=false`, `PAYMENTS_ARE_SIMULATED=false`, `DEBUG=false`
- [ ] All `change-me*` / `*_dev` secrets replaced
- [ ] Keycloak email verification enforced; privileged accounts bound explicitly
- [ ] TLS terminated; `ALLOWED_ORIGINS` locked to real origins
- [ ] PostgreSQL + object-storage backups configured and a restore tested
- [ ] ClamAV enabled and fail-closed
- [ ] Health checks and audit-log export wired up
- [ ] `pip-audit`, `trivy fs .`, and `npm --prefix frontend audit --omit=dev` reviewed
