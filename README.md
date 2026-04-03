# Michigan Unified E-Filing System (MUEFS)

A modern, open-source statewide e-filing platform for Michigan courts. Designed to unify filing across all 256 courts (Circuit, District, Probate, Court of Claims, Court of Appeals, Supreme Court) into a single, standards-compliant portal.

**Why this exists**: Michigan's current e-filing landscape is fragmented across multiple vendors and systems. Attorneys waste hours navigating incompatible platforms. Self-represented litigants face complex procedures with no guidance. MUEFS demonstrates that a unified, modern alternative is achievable.

## Demo Mode (No Docker Required)

```bash
git clone https://github.com/Tzodec1526/MUEFS.git
cd MUEFS/backend
pip install -e ".[test]"
python run_demo.py
```

This starts both backend and frontend using SQLite (no PostgreSQL/Docker needed):
- **Filing Portal**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

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
│   └── tests/         # 35 backend tests
├── frontend/          # React frontend
│   └── src/
│       ├── components/  # Filing wizard, clerk queue, case search
│       ├── api/         # API client
│       └── styles/      # Global CSS
└── docker-compose.yml
```

## Features

### For Attorneys
- **Unified filing** across all 256 Michigan courts from a single login
- **135+ MCR-referenced document types** with court rule guidance
- **Companion document alerts** — system tells you when a motion requires a brief (MCR 2.119), meet-and-confer certification (MCR 2.313), or proposed order
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

## Development

### Backend
```bash
cd backend
pip install -e ".[test]"
pytest tests/ -v          # Run 35 tests
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

## Michigan Court Coverage

| Court Type | Count | Jurisdiction |
|-----------|-------|-------------|
| Circuit Courts | 57 | General civil, criminal, family |
| District Courts | 110 | Limited civil, misdemeanors, traffic |
| Probate Courts | 83 | Estates, guardianships, mental health |
| Court of Claims | 1 | Claims against State of Michigan |
| Court of Appeals | 4 | Appellate review (4 districts) |
| Supreme Court | 1 | Final appellate authority |
| **Total** | **256** | **All 83 counties** |

## Compliance

- **MCR 1.109**: Text-searchable PDFs, electronic signatures, PII detection
- **MCR 2.002**: Fee waiver support for indigent filers
- **MCR 2.119**: Motion companion document requirements (brief, proposed order)
- **MCR 2.313**: Meet-and-confer certification for discovery motions
- **WCAG 2.1 AA**: Accessibility compliance
- **Security**: Content-type validation, input sanitization, rate limiting, audit logging

## License

MIT License — See [LICENSE](LICENSE) for details.

This project is open source to demonstrate that a unified Michigan e-filing system is technically achievable and to remove barriers to implementation.
