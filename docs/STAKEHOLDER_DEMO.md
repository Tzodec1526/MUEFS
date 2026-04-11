# Stakeholder demo — MUEFS

Use this for **live walkthroughs** (about 10–15 minutes). This build is a **product and workflow demonstration**, not a certified court production system.

## Before the meeting

1. **Host machine**: Run either:
   - **Fastest (no Docker):** `cd backend && pip install -e ".[test]" && python run_demo.py`  
     Then open **http://localhost:3000**
   - **Full stack:** `docker-compose up --build` from repo root, same URLs.
2. **Network**: For remote stakeholders, share your screen **or** tunnel `localhost:3000` with your org-approved tool (e.g. Teams screen share is usually enough).
3. **Browser**: Chrome or Edge; 1920×1080 or larger helps the filing wizard.

## URLs (local)

| What | URL |
|------|-----|
| Portal | http://localhost:3000 |
| API docs (optional) | http://localhost:8000/docs |

## How “login” works (demo)

There is **no password** in this mode. On the login page, pick a **role card**. That sets a demo session so the API knows whether you are an attorney, clerk, or self-represented user.

| Role | What to show |
|------|----------------|
| **Attorney** | Dashboard → **Case Search** → open a sample case → **File with Court** → start the filing wizard (documents, fees, validation). |
| **Court Clerk** | **Review Queue** (Wayne / 3rd Circuit in seed data) → open a pending filing → accept / return / reject with a reason. |
| **Self-represented** | Same as attorney; emphasize guided steps and fee waiver language in the wizard. |

Tip: Use **Switch Role** in the header to jump between attorney and clerk without restarting.

## Suggested script (10 minutes)

1. **Problem (1 min)** — Fragmented e-filing across vendors; one portal for all Michigan courts is the vision (see README comparison table).
2. **Attorney flow (4 min)** — Search → case detail → new filing → upload PDF → fee step (explain **simulated payment** in this demo).
3. **Clerk flow (3 min)** — Queue → review → decision → optional notification copy.
4. **Coverage (1 min)** — **Stats / coverage** dashboard if useful; 256 courts in seed narrative.
5. **Honest close (1 min)** — MVP; integrations (case management, payments, identity) are the next phase; security review before any production use.

## What to say about limitations

- **Identity**: Demo uses a **role picker**, not real attorney licensing or court SSO.
- **Payments**: **No money moves**; fees are calculated from schedules and recorded as simulated.
- **Documents**: No live virus scan / OCR pipeline in this build; validation is representative.
- **Court systems**: CMS adapters are structured but not connected to live JIS/Tyler instances.

## Automated testing (for facilitators / CI)

- **Backend:** From `backend/`, run `pip install -e ".[test]"` then `pytest tests/ -v`. This exercises filing rules, search, payments, auth policies, and **HTTP smoke** (`tests/test_http_smoke.py`: `/health`, `/docs`, unauthenticated search → 401).
- **Full browser demo:** There is **no Playwright/Cypress suite** yet; the role-picker UI is validated by **manual smoke** below.
- **Manual smoke (2 minutes):** Start `python run_demo.py` → open http://localhost:3000 → pick **Attorney** → **Case Search** runs → open a case → **New Filing** starts the wizard. Pick **Clerk** → **Review Queue** loads.

## If something breaks

- Restart `run_demo.py` or Docker Compose.
- Clear site **localStorage** for localhost (or use a private window) if the UI acts like the wrong user.
- Full **seed data** (many courts) requires a seeded DB; the quick demo uses SQLite + `run_demo.py` seed path documented in README.

## After the demo

- Point technical contacts to `README.md` (architecture, Docker) and API docs.
- For procurement or security conversations, lead with **MVP scope** and **integration checklist** (IdP, PSP, CMIS, hosting).
