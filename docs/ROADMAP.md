# Known Limitations & Roadmap

MUEFS is a working **proof of concept**. Every feature described in the README runs, but some
parts are deliberately demo-grade. This page is an honest accounting of what is
production-ready versus what is still a demonstration, so no one mistakes the demo for a
finished court system.

The implementation goal, current evidence and unresolved requirements are tracked in
[State implementation evaluation](STATE_READINESS.md). Retained submission receipts,
correction history and PostgreSQL concurrency checks now form part of the core workflow.

## Known limitations (demo-grade today)

- **CMS integration is not connected.** Demo acceptance records a simulated identifier.
  Outside demo mode, an unconfigured CMS blocks acceptance. No JIS or Tyler request is
  made; see the submission boundary in `backend/app/integrations/cms_adapter.py`.
- **Payments are simulated.** The fee/waiver flow is fully demonstrated, but no payment
  processor is integrated (`PAYMENTS_ARE_SIMULATED=true`); no card data is handled.
- **Demo auth is open by configuration.** The hosted demo enables `ALLOW_DEMO_MODE` and
  `ALLOW_PUBLIC_REGISTRATION` so anyone can explore it without an identity provider.
  Production runs Keycloak-only with no self-registration. See [SECURITY.md](../SECURITY.md).
- **Malware scanning defaults to the built-in heuristic.** Real signature-based scanning
  requires enabling the optional ClamAV backend.
- **Document validation is advisory.** MCR 1.109 checks (text-searchability, PII) produce
  warnings, not hard blocks, and PII detection is heuristic (regex), not exhaustive. Deeper
  processing (server-side OCR / PDF-A conversion) is not implemented.
- **Demo persistence is lightweight.** `run_demo.py` and the hosted demo use SQLite + local
  file storage; production uses PostgreSQL + MinIO/S3.
- **No e-service or email delivery.** Clerk decisions create in-app notifications.
  Service-only filings record documents; delivery must be arranged outside the app.

## Roadmap (illustrative)

- Live JIS / Tyler Odyssey adapter implementations: document-type mapping, real submission,
  and status sync against each court's Electronic Filing Manager.
- Payment-processor integration (PCI-scoped) replacing the simulated flow.
- Deeper MCR 1.109 processing: server-side OCR / PDF-A conversion and structured PII
  redaction (not just warnings).
- Broaden container hardening to the dev images and pin base images by digest (the
  production image already runs non-root with a healthcheck; CI security scanning and a
  [deployment guide](DEPLOYMENT.md) now exist).

> Courts and evaluators: if a capability matters for your evaluation and isn't listed here,
> please ask — this list reflects current scope, not a ceiling.
