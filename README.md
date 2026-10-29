# Michigan Unified E-Filing System (MUEFS)

Copyright (c) 2026 Thomas Cedoz. Licensed under [AGPL-3.0-or-later](LICENSE).

MUEFS is an open-source e-filing prototype for Michigan courts. The aim is one portal for
filing, court review and public records. [State implementation evaluation](docs/STATE_READINESS.md)
tracks the evidence for the implementation and the state requirements that remain.

Try the live demo at https://demo.tomcedoz.com.

## Why this exists

Today, e-filing in Michigan is split across several vendors and systems. Attorneys lose
hours moving between systems that do not work together. Self-represented litigants face
complex procedures with no guidance. MUEFS is an alternative with one login and one
interface for filing in Michigan's courts.

## MUEFS compared with MiFILE

| Capability | MiFILE and current systems | MUEFS (this demo) |
|---|---|---|
| Court coverage | Not all courts or case types | Demo portal (seeded courts) |
| Public docket search | Varies by court; often separate portals | Built in; no account needed in the demo |
| Document types | Varies by vendor | A catalog tied to the Michigan Court Rules (MCR); the count comes from the live seed data |
| Upload limit | 25 MB (SCAO standard) | 100 MB |
| Fee waiver (MCR 2.002) | Payment screen; court must grant | Part of the filing wizard (demo payments) |
| Motion companions | Filers must know MCR rules | Checks for them and prompts the filer (MCR 2.119) |
| File from the case docket | Existing-case filing supported | Filled in from the case page |
| Case favorites | Not available | Star cases for quick access |
| Service-only records | Varies; often a separate workflow | Keeps the documents, with opt-in delivery to reviewed recipients; other service methods stay outside the app |
| Draft editing | Depends on the vendor | Save to your account, recover edits in the same tab and compare conflicting versions |
| Clerk review tools | Queue tools vary by court | Batch accept, age badges and quick reject reasons |
| Case participants and access | Depends on the court | Assigned staff record roles and explicit access grants, and changes are kept |
| Reviewed public copies | Depends on the court | Prepare, check, publish and withdraw a separate PDF; the filed original is kept |
| Cost and license | Per-transaction vendor fees | AGPL-3.0 (no license fee) |

Status: this is an open-source demo. Filing, clerk review, public records, self-represented
filing and court administration work today. The payment processor and the live link to a
court's case management system (CMS) are still stubs. A state could choose and connect
those services as part of an implementation.

## Try it now

You can run the full demo with 4 commands. You don't need Docker or any database setup.

You need Python 3.11 or newer and Node.js 22.12 or newer (with npm).

```bash
git clone https://github.com/Tzodec1526/MUEFS.git
cd MUEFS/backend
pip install -e ".[test]"
python run_demo.py
```

- Filing portal: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

The launcher checks that ports 3000 and 8000 are free and installs any missing frontend
packages from the lockfile. It waits until the database and the frontend are ready before
it reports success. It listens only on this computer (the loopback interface). If startup
fails, or you press Ctrl+C, it stops the services it started. It keeps existing demo data and
upgrades it when needed, and it does not change your saved environment files. If a port is
already in use, stop that service before you run the demo. Restart the launcher after you
change backend code. It does not run a file watcher, which could interrupt a presentation.

Sign in as an Attorney, Court Clerk, System Administrator or Self-Represented Litigant, or
browse public court records without signing in.

The [demo walkthrough](demo/README.md) follows one fictional filing from start to finish:
preparing and submitting it, court review and acceptance, and the public docket. It has
sample PDFs and steps for showing all five roles.

## Architecture

- Backend: Python 3.11+ with FastAPI (async)
- Frontend: React 18, TypeScript and Vite
- Database: PostgreSQL 16 in production; SQLite in the demo
- Rate limiting: Redis 7 (shared) or in memory (demo)
- Object storage: S3-compatible storage in production (Versity Gateway in the Docker stack);
  the local filesystem in the demo
- Sign-in: Keycloak (OAuth2/OIDC) in production; a role picker in the demo
- Containers: Docker and Docker Compose

## Full local stack (Docker)

For a real (non-demo) deployment, follow [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). It
covers secrets, TLS, backups, ClamAV and the production settings. The commands below start
the full local stack with demo sign-in turned on. Its ports listen on this computer only.

```bash
git clone https://github.com/Tzodec1526/MUEFS.git
cd MUEFS
cp .env.example .env
docker compose up --build
```

Before the API and workers start, the one-time `migrate` service creates the document
bucket, applies the database migrations and seeds the demo data.

Services:

- Filing portal: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Keycloak admin: http://localhost:8080
- Document storage (S3 API): http://localhost:7070

Besides the demo role cards, the stack loads a local Keycloak realm
([keycloak/muefs-realm.json](keycloak/muefs-realm.json)). It has one self-represented
litigant account, so you can try signing in through the identity provider. The account's
credentials are in that file. They are for local evaluation only.

## Project structure

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

### For attorneys

- File with Michigan courts from a single login.
- Pick from document types tied to the Michigan Court Rules, with court-rule guidance. The
  dashboard shows the current count.
- The system tells you when a motion needs a companion document: a brief (MCR 2.119), a
  meet-and-confer certification (MCR 2.313) or a proposed order.
- File a motion in one click: open a case and click "File with Court". The court, case and
  case type are filled in for you.
- Star cases so you can find them quickly in later sessions.
- Save drafts to your account. You can recover unsaved edits in the same browser tab, and
  compare conflicting changes before you replace the saved details.
- Checks before submission catch errors before clerk review.
- Submission receipts and a correction history: time-stamped lists of the documents filed,
  the earlier versions that were kept, clerk decisions and receipts you can download.
- Court calendars have published revisions for time zones, holidays and closures. The time
  a filing was received and its date-only filing date are recorded separately, and the
  history of each date calculation is kept.

### For self-represented litigants

- The guided filing wizard gives plain-language instructions.
- Fee waiver review: you upload the application privately, and clerks and judges make
  separate decisions. Signed orders are kept, and after a denial you can pay (with external
  receipt credits or demo payments).
- Court fee review: ask for an itemized assessment and see the remaining balance. When the
  court changes the amount, your earlier payment credits are kept.
- The process goes step by step, so no legal knowledge of e-filing procedures is needed.

### For court clerks

- The workspace covers every court you are assigned to. Switch between them to review
  filings, fees, case records and notices, and refresh your assignments without signing
  out.
- The fee assessment queue shows the filer's documents and reason for review. Clerks record
  itemized charges and their authority, and earlier assessments and payment history are
  kept.
- External receipt credits: court administrators who are explicitly assigned can record
  verified receipts, recover lost responses and reverse credits entered in error. The
  evidence is kept. This optional workflow does not collect money or give refunds.
- The court receipt register lets assigned administrators review credits and reversals by
  the period they were recorded in. They can compare the separate simulation totals and
  export the matching activity.
- The review queue has batch accept, age tracking and common rejection reasons.
- Document checks cover text searchability, file format and size limits.
- Filing status notices: a history in the portal, plus optional email alerts over SMTP.
  Delivery attempts are kept, failed sends can be recovered, and the court reviews emails
  whose outcome is uncertain.

### For court administration

- Private case archives: export linked case records and every kept version of each
  document, with a manifest that can be verified, for records transfer. See
  [case export](docs/CASE_EXPORT.md).
- People and access: set up accounts explicitly and hand court administration to
  delegates. Grant and remove staff assignments, deactivate accounts and look at the kept
  record of changes.
- Scoped administration: court delegates manage their own court's staff. System
  administrators control identity bindings and administrator rights.
- The system shows counts of courts, users, cases, filings and pending reviews.
- It is open source, with no vendor lock-in.

### For the public and press

- Open docket search: find cases that are not sealed by part of the case number or by
  party name, and filter by court. You can share the filtered results without an account.
  When case numbers overlap across courts, the results show the court and county.
- Download public documents from accepted filings, and public copies the court has
  reviewed, subject to any restrictions on the case.
- Assigned staff can withdraw public access without deleting the original, earlier copies
  or the transaction history.

## Development

### Backend

```bash
cd backend
pip install -e ".[test]"
pytest tests/ -v          # Run full suite (includes HTTP smoke: /health, /docs)
DEBUG=true uvicorn app.main:app --reload   # Without DEBUG, production startup checks apply
```

#### Service-backed tests

Some tests need disposable services and are skipped without them. Point these variables at
throwaway instances only; the tests create and drop their own schemas and buckets:

- `MUEFS_TEST_POSTGRES_URL`: a PostgreSQL 16 database, for example
  `postgresql+asyncpg://postgres:test-only@127.0.0.1:5432/muefs_test`
- `MUEFS_TEST_S3_ENDPOINT`, `MUEFS_TEST_S3_ACCESS_KEY`, `MUEFS_TEST_S3_SECRET_KEY`: an
  S3-compatible endpoint on this computer (the CI job uses Versity Gateway)
- `MUEFS_TEST_CLAMAV_PORT`: a ClamAV daemon on 127.0.0.1 using `clamav/clamd.conf` and
  `clamav/muefs-limits.cdb`

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) shows how CI starts all three.

#### Reseeding demo data

Seeding runs only once. After that it skips, so a database keeps its old seed data even
after `app/seed_data.py` changes. To seed again:

```bash
docker compose exec backend python -m app.seed_data --reset   # Docker stack
rm backend/demo.db                                            # run_demo.py reseeds on next start
```

`--reset` drops and recreates only the application tables. It leaves Keycloak's tables and
stored documents alone. To start completely fresh (all volumes, including uploaded
documents), run `docker compose down -v && docker compose up --build`.

A fresh seed includes real sample PDFs. Each one is clearly marked as a sample, and its file
hash and size match its record. The sample attorney has reviewed filing access to the
Johnson and Williams cases, and the self-represented user has reviewed access to Williams.
Existing databases keep their access decisions. An assigned clerk can review those grants
through Manage case access on the docket.

An upgrade keeps existing document details and receipts. It does not make up files for
older demo rows. To get the new samples, rebuild only demo data you can throw away. If a
stored file is missing or changed, submission and acceptance are blocked until the original
is restored or the draft attachment is replaced.

### Frontend

```bash
cd frontend
npm install
npm run dev               # Development server
npx tsc --noEmit          # Type check
npm run build             # Production build
```

From the repo root you can also run `npm run dev` (full demo stack), `npm test`, and `npm run lint`.

## Security and compliance

The public demo is open to anyone, but its security rules still apply. The server enforces
them, and the test suite covers them. See [SECURITY.md](SECURITY.md) for the full security
model, the threat boundaries and the hardening guide.

### Security

- Sealed cases need an explicit grant on a participant record, or an authorized court or
  system role. A grant for a lawyer also needs a linked account and a matching, verified bar
  number. An original document that is restricted on its own stays available only to the
  filer and the assigned court staff.
- Before publishing, staff check a separate PDF and an approved title. Publishing restricts
  the original. Withdrawing removes the active copy but does not restore the original. The
  court supplies the redactions and the authority; automated scanning does not certify that
  a release is safe.
- Document and waiver uploads keep request keys. If a response is lost, the upload can be
  retried without a duplicate document, a second screening or another fee revision. A
  changed request, or a retry after removal, returns a conflict.
- Every upload is screened for malware before it is stored, and uploads that fail are
  rejected. The screening uses a built-in check for executables and the EICAR test file,
  plus optional ClamAV.
- Text sampled from each PDF is checked for likely Social Security numbers (SSNs), dates of
  birth and account numbers. Validation reuses those warnings; the check does not certify
  redaction.
- Before a filing is submitted or accepted, the system reads every current attachment. Each
  one's SHA-256 hash and byte count must match the uploaded record.
- A [read-only storage audit](docs/STORAGE_RECOVERY.md) checks restored files, archived
  copies and the kept transaction fingerprints, and streams a report.
- Sign-in uses Keycloak RS256 JWTs. The API checks the signature, issuer and expiry, and it
  does not accept the `none` algorithm. Automatic account creation on first OIDC sign-in needs
  a verified email, and it won't take over privileged accounts.
- Every object has audit logging and ownership checks, and all queries are parameterized.

### Court-rule features and evaluation

- MCR 1.109: text-searchable PDFs, electronic signatures and detection of personal
  information (PII).
- MCR 2.002: fee waivers for filers who cannot afford the fees.
- MCR 2.119: companion documents for motions (brief, proposed order).
- MCR 2.313: a meet-and-confer certification for discovery motions.
- Accessibility needs an independent conformance evaluation. Responsive layouts and keyboard
  controls alone do not show WCAG compliance.

### Why this is lower-risk than the status quo

MUEFS is one open-source codebase that can be audited, with a documented security review and
`SECURITY.md`, instead of several closed vendor systems. There is no lock-in: identity,
payments and the system-of-record CMS stay with the court (see the threat-boundary table in
SECURITY.md).

## Known limitations and roadmap

MUEFS is a working proof of concept. Some parts (the live CMS integration and payments) are
demo-only on purpose. [docs/ROADMAP.md](docs/ROADMAP.md) lists what is ready for production
and what is only a demonstration, plus the planned roadmap.

## License

MUEFS is licensed under AGPL-3.0. See [LICENSE](LICENSE) for details.

This project is open source to remove barriers to building a unified e-filing system for
Michigan.
