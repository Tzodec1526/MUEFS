# Michigan Unified E-Filing System (MUEFS)

Copyright (c) 2026 Thomas Cedoz. Licensed under [AGPL-3.0-or-later](LICENSE).

An open-source e-filing prototype for Michigan courts. The aim is one portal for filing,
court review and public records, with the implementation evidence and remaining state
requirements tracked in [State implementation evaluation](docs/STATE_READINESS.md).

Live demo: https://webmcp.tomcedoz.com/agent · https://demo.tomcedoz.com · Agent tools: [docs/WEBMCP.md](docs/WEBMCP.md)

**Why this exists**: Michigan's current e-filing landscape is fragmented across multiple vendors and systems. Attorneys waste hours navigating incompatible platforms. Self-represented litigants face complex procedures with no guidance. MUEFS is a unified, modern alternative — one login and one interface for filing across Michigan's courts.

## MUEFS vs MiFILE

| Capability | MiFILE / current landscape | MUEFS (this demo) |
|---|---|---|
| **Court coverage** | Not all courts or case types | Demo portal (seeded courts) |
| **Public docket search** | Varies by court; often separate portals | Built-in; no account in demo |
| **Document types** | Varies by vendor | MCR-referenced catalog (count from live seed data) |
| **Upload limit** | 25 MB (SCAO standard) | 100 MB |
| **Fee waiver (MCR 2.002)** | Payment screen; court must grant | In filing wizard (demo payments) |
| **Motion companions** | Filers must know MCR rules | Validates & prompts (MCR 2.119) |
| **File from case docket** | Existing-case filing supported | Pre-filled from case detail |
| **Case favorites** | Not available | Star cases, quick access |
| **Service-only records** | Varies; often separate workflow | Retained documents and opt-in delivery to reviewed recipients; other service methods remain external |
| **Draft editing** | Vendor-dependent | Save to account, recover edits within a tab, and compare conflicting versions |
| **Clerk review tools** | Queue tools vary by court | Batch accept, age badges, quick reject reasons |
| **Case participants and access** | Court-dependent | Assigned staff record roles, explicit access grants and retained changes |
| **Reviewed public copies** | Court-dependent | Prepare, inspect, publish and withdraw a separate PDF; retain the filed original |
| **AI agent tools (WebMCP)** | Not available | 20 role-aware tools + `/agent` hub |
| **Cost / licensing** | Per-transaction vendor fees | AGPL-3.0 (no license fee) |

> **Status:** Open source demo — filing, clerk review, public records, self-represented filing, and court administration work today. The payment processor and live court CMS integration remain **stubs**. A state could select and connect those services as part of an implementation.

---

## Try It Now

Clone and run the full demo in 4 commands — no Docker, no database setup:

```bash
git clone https://github.com/Tzodec1526/MUEFS.git
cd MUEFS/backend
pip install -e ".[test]"
python run_demo.py
```

- **Filing Portal**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

Log in as an **Attorney**, **Court Clerk**, **System Administrator**, or **Self-Represented Litigant**, or **browse public court records without signing in**.

Watch the **[complete attorney walkthrough](demo/muefs-attorney-flow.mp4)** from sign-in through document uploads, simulated payment, and the submission receipt. To record every role, follow the **[five-role recording guide](demo/README.md)**, which includes sample PDFs and a sequence through clerk acceptance, public search, a fee waiver request, and court access administration.

---

## Architecture

- **Backend**: Python 3.11+ / FastAPI (async)
- **Frontend**: React 18 + TypeScript + Vite
- **Database**: PostgreSQL 16 (production) / SQLite (demo)
- **Rate limiting**: Redis 7 (shared) / memory (demo)
- **Object Storage**: MinIO S3-compatible (production) / local filesystem (demo)
- **Auth**: Keycloak OAuth2/OIDC (production) / role-based demo login (demo)
- **Containerization**: Docker + Docker Compose

## Production Setup (Docker)

> For a real (non-demo) deployment — secrets, TLS, backups, ClamAV, and the production
> toggles — follow **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**. The commands below bring up
> the full local stack.

```bash
git clone https://github.com/Tzodec1526/MUEFS.git
cd MUEFS
cp .env.example .env
docker-compose up --build
```

Services:
- **Filing Portal**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Keycloak Admin**: http://localhost:8080

## Project Structure

```
MUEFS/
├── backend/           # FastAPI backend API
│   ├── app/
│   │   ├── api/       # REST endpoints
│   │   ├── models/    # SQLAlchemy models
│   │   ├── schemas/   # Pydantic schemas
│   │   ├── services/  # Business logic
│   │   └── seed_data.py  # Michigan court data
│   └── tests/         # backend tests (pytest + HTTP smoke)
├── frontend/          # React frontend
│   └── src/
│       ├── components/  # Filing wizard, clerk queue, case search
│       ├── api/         # API client
│       └── styles/      # Global CSS
└── docker-compose.yml
```

## Features

### For Attorneys
- **Unified filing** across Michigan courts from a single login
- **MCR-referenced document types** (live count on the dashboard) with court rule guidance
- **Companion document alerts** — system tells you when a motion requires a brief (MCR 2.119), meet-and-confer certification (MCR 2.313), or proposed order
- **One-click motion filing** — open a case, click "File with Court", and court/case/type are pre-filled
- **Case favorites** — star cases for quick access across sessions
- **Draft saves and recovery** — save work to your account, recover unsaved edits in the same tab, and compare conflicting changes before replacing saved details
- **Pre-submission validation** — catch errors before clerk review
- **Submission receipts and correction history** — timestamped document manifests,
  retained earlier versions, clerk decisions and downloadable receipts
- **Court calendars and filing dates** — published timezone/holiday/closure revisions,
  separate receipt timestamps and date-only filing records, with preserved calculation history

### For Self-Represented Litigants
- **Guided filing wizard** with plain-language instructions
- **Fee waiver review**: private application uploads, separate clerk/judicial decisions,
  retained signed orders and payment after denial (external receipt credits or demo payments)
- **Court fee review**: request an itemized assessment, see the remaining balance and
  retain earlier payment credits when the court revises the amount
- **Step-by-step process** — no legal knowledge of e-filing procedures required

### For Court Clerks
- **Assigned court workspace**: switch between authorized courts for filing review, fees,
  case records and notices; refresh assignments without signing out
- **Fee assessment queue**: inspect the filer's documents and review reason, record
  itemized charges and authority, and preserve earlier assessments and payment history
- **External receipt credits**: explicitly assigned court administrators can record verified
  receipts, recover lost responses and reverse erroneous credits with retained evidence.
  This optional workflow does not collect funds or issue refunds.
- **Court receipt register**: assigned administrators review credits and reversals by
  recorded period, compare separate simulation totals and export the matching activity.
- **Review queue** with batch accept, age tracking, and common rejection reasons
- **Document compliance checks** — text-searchability, file format, size limits
- **Filing status notices** — portal history plus optional SMTP alerts, retained attempts,
  failure recovery and court review of uncertain email outcomes

### For Court Administration
- **Private case archives** — export linked case records and every retained document version
  with a verifiable manifest for records transfer; see [case export](docs/CASE_EXPORT.md)
- **People & access** — explicitly provision identities, delegate court administration,
  grant and revoke staff assignments, deactivate accounts and inspect retained changes
- **Scoped administration** — court delegates manage their own court's staff; system
  administrators control identity bindings and administrator privileges
- **System counts** — courts, users, cases, filings and pending reviews
- **Open source** — no vendor lock-in, transparent, community-driven

### For the Public & Press
- **Open docket search** — find non-sealed cases by partial number or party name, filter by court, and share the filtered results without an account. Results identify the court and county when numbers overlap across courts.
- **Public document access** — download public documents on accepted filings and court-reviewed public copies, subject to case restrictions
- **Controlled publication** — assigned staff can withdraw public access without deleting the original, earlier copies or transaction history

## Development

### Backend
```bash
cd backend
pip install -e ".[test]"
pytest tests/ -v          # Run full suite (includes HTTP smoke: /health, /docs)
uvicorn app.main:app --reload
```

#### Reseeding demo data

Seeding runs once and then skips, so a database keeps old seed data after
`app/seed_data.py` changes. To reseed:

```bash
docker compose exec backend python -m app.seed_data --reset   # Docker stack
rm backend/demo.db                                            # run_demo.py reseeds on next start
```

`--reset` drops and recreates only the application tables — Keycloak's tables and
stored documents are untouched. For a fully clean slate (all volumes, including
uploaded documents), use `docker compose down -v && docker compose up --build`.

Fresh seeds include real, visibly marked sample PDFs with matching file hashes and sizes.
An upgrade preserves existing document metadata and receipts; it does not fabricate files
for older demo rows. Rebuild only disposable demo data to get the new samples. A missing
or altered stored file blocks submission and acceptance until the original is restored
or a draft attachment is replaced.

### Frontend
```bash
cd frontend
npm install
npm run dev               # Development server
npx tsc --noEmit          # Type check
npm run build             # Production build
```

From the repo root you can also run `npm run dev` (full demo stack), `npm test`, and `npm run lint`.

#### WebMCP

- **`/agent`** — tool catalog, workflows, activity feed, example prompts
- **Workflows:** `attorney_motion_workflow`, `clerk_triage_workflow`
- **20 tools**, role-filtered (public / filer / clerk)

Guide: **[docs/WEBMCP.md](docs/WEBMCP.md)**

## Security & Compliance

Opening the public demo's *front door* never opens the *rooms inside* — application-layer
security is enforced server-side and covered by the test suite. See **[SECURITY.md](SECURITY.md)**
for the full security model, threat boundaries, and hardening guide.

**Security**
- **Sealed case access** — requires an explicit participant grant or authorized court/system role. Counsel grants require a linked account and matching verified bar number. Individually restricted originals remain available only to the filer and assigned court staff.
- **Reviewed public copies** — staff inspect a separate PDF and approved title before publishing. Publication restricts the original; withdrawal removes the active copy without restoring the original. The court supplies redactions and authority; automated scanning does not certify a safe release.
- **Upload recovery** — document and waiver uploads retain request keys so a lost response
  can be retried without duplicate documents, repeated screening or another fee revision.
  Changed requests and retries after removal return a conflict.
- **Upload malware screening** — every upload is screened (built-in executable/EICAR heuristic, optional ClamAV) and rejected before storage.
- **Retained upload screening** — sampled PDF text is checked for likely SSNs, dates of
  birth and account numbers. Validation reuses those warnings; it does not certify redaction.
- **Stored-file integrity** — submission and acceptance stream every current attachment
  and require its SHA-256 and byte count to match the uploaded record before proceeding.
- **Recovery verification** — a [read-only storage audit](docs/STORAGE_RECOVERY.md) checks
  restored files, archived copies and retained transaction fingerprints with a streamed report.
- **Hardened authentication** — Keycloak RS256 JWTs (signature, issuer, expiry verified; no `none` algorithm); OIDC auto-provisioning requires a verified email and won't adopt privileged accounts.
- **Audit logging & ownership checks** on every object, with parameterized queries throughout.

**Court-rule features and evaluation**
- **MCR 1.109** — text-searchable PDFs, electronic signatures, PII detection
- **MCR 2.002** — fee waiver support for indigent filers
- **MCR 2.119** — motion companion documents (brief, proposed order)
- **MCR 2.313** — meet-and-confer certification for discovery motions
- Accessibility requires an independent conformance evaluation; responsive layouts and
  keyboard controls alone do not establish WCAG compliance.

**Why this is lower-risk than the status quo:** one auditable, open-source codebase (shipping
a documented security review and `SECURITY.md`) instead of multiple closed vendor systems —
and no lock-in: identity, payments, and the system-of-record CMS stay with the court (see the
threat-boundary table in SECURITY.md).

## Known Limitations & Roadmap

MUEFS is a working proof of concept — some parts (live CMS integration, payments) are
deliberately demo-grade. See **[docs/ROADMAP.md](docs/ROADMAP.md)** for an honest accounting
of what is production-ready vs. demonstration, plus the planned roadmap.

## License

AGPL-3.0 License — See [LICENSE](LICENSE) for details.

This project is open source to remove the barriers to building a unified Michigan e-filing system.
