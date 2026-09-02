---
name: verify-muefs
description: Drive the MUEFS demo filing portal (web UI at http://127.0.0.1:3000) the way a user does — launch the SQLite demo stack, doctor the instance, and prove login, public case search, the filing wizard, the clerk review queue, and the Agent Hub. Use when verifying MUEFS UI or API user-facing behavior after a change, or when a proof of the real user path is required.
---

# Verify MUEFS

MUEFS is a Michigan e-filing demo. The surface an agent must drive is the **Filing Portal** (React + Vite) at `http://127.0.0.1:3000`, talking to the FastAPI demo API at `http://127.0.0.1:8000`. Secondary surfaces: `/docs` OpenAPI, HTTP `/api/v1/*`, WebMCP tools on `/agent`. Production Docker/Keycloak is out of scope for this skill.

Read `features/README.md` before driving, then the matching feature file. A proof that hits one convenient entry point is incomplete when the map lists others.

Helper (repo root):

```text
node .cursor/skills/verify-muefs/helpers/control-muefs.mjs <command>
```

## Launch

Default demo ports are **hardcoded**: frontend `3000`, API `8000`, SQLite `backend/demo.db`. Two instances cannot run side by side. Refusing to double-drive a shared instance beats corrupting a session already on those ports.

1. From the repo root, start the stack this run owns:

```text
node .cursor/skills/verify-muefs/helpers/control-muefs.mjs launch
```

That runs `backend/run_demo.py` (same as `npm run dev`): SQLite seed, uvicorn on `8000`, Vite on `3000` with `VITE_ALLOW_DEMO_MODE=true`. Ready when `GET http://127.0.0.1:8000/health` returns `{"status":"healthy","service":"muefs-api"}` and `GET http://127.0.0.1:3000/` contains `Michigan Unified E-Filing System`. Timeout is 90s; logs go to `.cursor/skills/verify-muefs/.run/demo.log`.

2. If launch refuses because ports are occupied: stop that demo, or attach read-aware with `MUEFS_VERIFY_ATTACH=1` (cleanup will **not** kill an attached process).

3. Teardown: `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs cleanup` — kills only the PID tree this run started. Proof artifacts stay in `.cursor/skills/verify-muefs/artifacts/`.

First-time machine: `pip install -e ".[test]"` in `backend/` and `npm install` in `frontend/` (Playwright lives there). Chromium: `cd frontend && npx playwright install chromium`.

## Doctor

Run first whenever anything looks off:

```text
node .cursor/skills/verify-muefs/helpers/control-muefs.mjs doctor
```

Pass means: API health JSON is `muefs-api` / `healthy`, the portal HTML identifies MUEFS, and either this run owns the demo PID or attach was explicit. Fail means do not drive.

## Drive

Use Playwright through `control-muefs browser`, not coordinates. Prefer ARIA roles, accessible names, and `label`/`htmlFor` over CSS. Demo auth is `localStorage.demo_role`; the stable way to set it is `/login?role=attorney|clerk|srl|public` (auto-applies and navigates).

```text
node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=attorney
node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Search"
node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser fill --label "Party Name" --value Smith
node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Results"
node .cursor/skills/verify-muefs/helpers/control-muefs.mjs api get /api/v1/cases/search?party_name=Smith --path artifacts/case-search/search.json
```

Each `browser` command POSTs to a long-lived Chromium the helper starts on first use (`.run/browser.port`). In-page state survives fill → click → snapshot until `cleanup`. Case search also writes the query to the URL (`?party=Smith`).

Do not call internal setters or test-only endpoints as the user path. `/api/v1/cases/search` is the same public search the UI uses — allowed as a **second view** of stored results, not as a substitute for clicking Search.

## Evidence

Put proof under `.cursor/skills/verify-muefs/artifacts/<feature-id>/`. Cleanup must not delete that tree.

- Capture the **action and the resulting state**, not only the final screen.
- UI proof: snapshot (`browser snapshot --path …`, Playwright ARIA yaml with text fallback) and a screenshot that shows the MUEFS header identity (`Michigan Unified E-Filing System`).
- HTTP second view: response body + status for the matching `/api/v1` read.
- Mutation proof (favorites, clerk accept/return): a read-only second view of the stored value. Clerk accept/reject **writes `backend/demo.db`** — do not use those as the default proof; they dirty the shared demo database.
- Record the feature ID and entry point with every artifact (filename under the feature folder is enough).
- Mocks only at production boundaries this demo already stubs (CMS, payments). Do not stub the portal or the search API.

## Cleanup

```text
node .cursor/skills/verify-muefs/helpers/control-muefs.mjs cleanup
```

Kills the process tree of the PID recorded at launch (`taskkill /T` on Windows). Never kill by image name (`python`, `node`, `uvicorn`). Attached instances stay up. Removes `.run/state.json` and the browser profile. Leaves `artifacts/`.

## Helpers

| Command | Purpose |
|---|---|
| `launch` | Start `run_demo.py` if ports are free; reuse if this PID still owns them |
| `doctor` | Read-only health + ownership check |
| `cleanup` | Stop owned PID tree; keep artifacts |
| `browser goto <path>` | Open a portal path |
| `browser click --role <role> --name <name>` | Click by role + accessible name (substring) |
| `browser fill --label <label> --value <text>` | Fill a labelled field |
| `browser wait --role --name` | Wait until visible |
| `browser snapshot --path <file>` | Write ARIA snapshot |
| `browser screenshot --path <file>` | Viewport screenshot |
| `api get <path> --path <file>` | GET the API (second view) |

`--exact` makes role-name matching exact. `MUEFS_VERIFY_HEADED=1` opens a visible browser. `MUEFS_FRONTEND_URL` / `MUEFS_API_URL` override defaults only if you actually launched on those URLs — `run_demo.py` does not remap ports.

## Isolate

Cannot run two demos. Ports and `backend/demo.db` are shared by design. One verification owner at a time.
