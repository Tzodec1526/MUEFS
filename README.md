# Michigan Unified E-Filing System (MUEFS)

A modern, open-source statewide e-filing platform for Michigan courts. Designed to unify filing across all 242+ trial courts (Circuit, District, Probate) and appellate courts into a single, standards-compliant portal.

## Architecture

- **Backend**: Python 3.12 + FastAPI (async)
- **Frontend**: React 18 + TypeScript + Vite
- **Database**: PostgreSQL 16
- **Cache/Queue**: Redis 7 + Celery
- **Object Storage**: MinIO (S3-compatible)
- **Auth**: Keycloak (OAuth2/OIDC)
- **Containerization**: Docker + Docker Compose

## Quick Start

```bash
# Clone and start all services
git clone https://github.com/Tzodec1526/Plague.git
cd Plague
cp .env.example .env
docker-compose up --build
```

Services will be available at:
- **Filing Portal**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Keycloak Admin**: http://localhost:8080

## Project Structure

```
plague/
├── backend/          # FastAPI backend API
├── frontend/         # React frontend application
├── docs/             # Architecture and API documentation
├── infrastructure/   # Kubernetes and Terraform configs
└── docker-compose.yml
```

## Development

### Backend
```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Running Tests
```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm test
```

## Compliance

- **MCR 1.109**: Text-searchable PDFs, electronic signatures, PII redaction
- **OASIS LegalXML ECF 4.01**: Standards-compliant filing format
- **WCAG 2.1 AA**: Accessibility compliance
- **Security**: OAuth2/OIDC, AES-256 encryption, SHA-256 document integrity

## Michigan Court Coverage

Designed to serve all Michigan courts:
- 57 Circuit Courts (general jurisdiction)
- 105 District Courts (limited jurisdiction)
- 78 Probate Courts
- Court of Appeals (4 districts)
- Supreme Court

## License

MIT License - See [LICENSE](LICENSE) for details.
