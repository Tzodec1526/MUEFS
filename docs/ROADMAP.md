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
  warnings, and PII detection samples at most five pages using heuristics. Those upload
  results are retained and reused; legacy documents without results carry an explicit
  review warning. PDF uploads must be readable, and submission/acceptance block when stored
  bytes fail hash/size verification. Deeper processing (server-side OCR / PDF-A conversion)
  is not implemented, and storage retention/recovery still requires operational validation.
- **Demo persistence is lightweight.** `run_demo.py` and the hosted demo use SQLite + local
  file storage; production uses PostgreSQL + MinIO/S3.
- **Electronic service is not implemented.** An opt-in SMTP outbox sends generic filing
  alerts to verified accounts and retains transport outcomes. Those alerts do not establish
  legal service. Service-only filings record documents; delivery must be arranged outside
  the app. A court-approved relay, bounce handling and service procedures remain necessary.
- **Participant records require court review.** Staff can record parties, counsel and
  explicit restricted-case grants with retained authority and history. The portal does not
  determine legal appearance, approve withdrawal or enroll a service contact. Legacy
  participant links require review after migration; accepting a filing grants no case role.
- **Public copies require human review.** Assigned staff can prepare a separate PDF,
  inspect it, publish its approved title and later withdraw public access while retaining
  originals, copies and history. Redactions are prepared using the court's approved tools;
  the sampled PII scan does not certify them. Case/document classification policy, records
  retention schedules and protected storage still require court approval and validation.

## Roadmap (illustrative)

- Live JIS / Tyler Odyssey adapter implementations: document-type mapping, real submission,
  and status sync against each court's Electronic Filing Manager.
- Payment-processor integration (PCI-scoped) replacing the simulated flow.
- Deeper MCR 1.109 processing: server-side OCR / PDF-A conversion and redaction tooling
  to support the existing court-reviewed public-copy workflow.
- Broaden container hardening to the dev images and pin base images by digest (the
  production image already runs non-root with a healthcheck; CI security scanning and a
  [deployment guide](DEPLOYMENT.md) now exist).

> Courts and evaluators: if a capability matters for your evaluation and isn't listed here,
> please ask — this list reflects current scope, not a ceiling.
