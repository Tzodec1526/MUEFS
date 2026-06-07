# Michigan Unified E-Filing System (MUEFS)

A modern, open-source statewide e-filing platform for Michigan courts. Designed to unify filing across all of Michigan's courts into a single, standards-compliant portal.

**Why this exists**: Michigan's current e-filing landscape is fragmented across multiple vendors and systems. Attorneys waste hours navigating incompatible platforms. Self-represented litigants face complex procedures with no guidance. MUEFS is a unified, modern alternative — one login and one interface for filing across Michigan's courts.

## MUEFS vs MiFILE

| Feature | MiFILE (Current) | MUEFS |
|---|---|---|
| **Court coverage** | Fragmented across vendors | All Michigan courts, one login |
| **Public records access** | Separate systems, varies by court | Statewide docket search & public document download, no account needed |
| **Document types** | Varies by vendor | 135+ MCR-referenced types |
| **Upload limit** | 25 MB | 100 MB |
| **Fee waiver (MCR 2.002)** | Manual/unclear | Built into payment flow |
| **Motion companions** | No guidance | Auto-prompts for briefs, proposed orders (MCR 2.119) |
| **Case favorites** | Not available | Star cases, quick access across sessions |
| **One-click motion filing** | Re-enter case info every time | Pre-fills court, case, type from case detail |
| **Clerk review tools** | Basic | Batch accept, age tracking, common rejection reasons |
| **Cost model** | Per-transaction vendor fees | Open source, no licensing fees |
| **Vendor lock-in** | Yes | AGPL-3.0, community-driven |

> **Status:** Open source and under active development — core filing, clerk review, and public docket search work today.

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

Log in as an **Attorney**, **Court Clerk**, or **Self-Represented Litigant**, or **browse public court records without signing in**.

---

## Architecture

- **Backend**: Python 3.11+ / FastAPI (async)
- **Frontend**: React 18 + TypeScript + Vite
- **Database**: PostgreSQL 16 (production) / SQLite (demo)
- **Cache/Queue**: Redis 7 + Celery
- **Object Storage**: MinIO S3-compatible (production) / local filesystem (demo)
- **Auth**: Keycloak OAuth2/OIDC (production) / role-based demo login (demo)
- **Containerization**: Docker + Docker Compose

## Production Setup (Docker)

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
- **135+ MCR-referenced document types** with court rule guidance
- **Companion document alerts** — system tells you when a motion requires a brief (MCR 2.119), meet-and-confer certification (MCR 2.313), or proposed order
- **One-click motion filing** — open a case, click "File with Court", and court/case/type are pre-filled
- **Case favorites** — star cases for quick access across sessions
- **Auto-save drafts** — never lose work in progress
- **Pre-submission validation** — catch errors before clerk review

### For Self-Represented Litigants
- **Guided filing wizard** with plain-language instructions
- **Fee waiver support** (MCR 2.002) built into the payment flow
- **Step-by-step process** — no legal knowledge of e-filing procedures required

### For Court Clerks
- **Review queue** with batch accept, age tracking, and common rejection reasons
- **Document compliance checks** — text-searchability, file format, size limits
- **Real-time filing status** updates with notifications

### For Court Administration
- **Statewide analytics** — filing volumes, processing times, court coverage
- **Open source** — no vendor lock-in, transparent, community-driven
- **Cost savings** — one system replaces multiple vendor contracts

### For the Public & Press
- **Open docket search** — look up any non-sealed case by number or party name, no account required
- **Public document access** — view dockets and download non-confidential filings; sealed cases and confidential documents stay restricted to parties and court staff
- **Transparency by default** — court records are open by default, protected where the rules require

## Development

### Backend
```bash
cd backend
pip install -e ".[test]"
pytest tests/ -v          # Run full suite (includes HTTP smoke: /health, /docs)
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev               # Development server
npx tsc --noEmit          # Type check
npm run build             # Production build
```

## Compliance

- **MCR 1.109**: Text-searchable PDFs, electronic signatures, PII detection
- **MCR 2.002**: Fee waiver support for indigent filers
- **MCR 2.119**: Motion companion document requirements (brief, proposed order)
- **MCR 2.313**: Meet-and-confer certification for discovery motions
- **WCAG 2.1 AA**: Accessibility compliance
- **Security**: Content-type validation, input sanitization, rate limiting, audit logging

## License

AGPL-3.0 License — See [LICENSE](LICENSE) for details.

This project is open source to remove the barriers to building a unified Michigan e-filing system.
