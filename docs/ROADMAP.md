# Known Limitations & Roadmap

MUEFS is a working **proof of concept**. Every feature described in the README runs, but some
parts are deliberately demo-grade. This page is an honest accounting of what is
production-ready versus what is still a demonstration, so no one mistakes the demo for a
finished court system.

## Known limitations (demo-grade today)

- **CMS integration is stubbed.** The adapter layer (JIS, Tyler Odyssey) is real and
  pluggable, and dispatches by `court.cms_type`, but the adapters return canned responses —
  there is no live connection to a court case-management system yet. See
  `backend/app/integrations/`.
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
- **No production e-service or notice delivery.** The demo captures email via MailHog rather
  than sending real notices.

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
