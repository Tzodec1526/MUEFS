# Agent Hub

The Agent Hub at `/agent` is a public catalog of the WebMCP tools registered for the current role, plus a declarative case search, an activity feed and copyable example prompts.

## Sub-features

- `hub-open` shows heading `MUEFS Agent Hub` with sections WebMCP, Activity, Case search, Workflows, Discovery, Prompts (and Actions when the role has action tools).
- `hub-search` runs the hub `search_cases_form` form (Party name, default Smith) and lists hits with `Open`.
- `hub-open-docket` follows a hit's `Open` link to that case's docket.

## How to get to it (user POV)

- Open `/agent` (no account required).
- Sidebar `Agent Hub` when WebMCP is available in the browser.
- Header WebMCP link (when shown).
- Hub nav `Sign in`, `Case search`, `App home`.

## Driving it with control-muefs

Preconditions:

- MUEFS is healthy at `http://127.0.0.1:3000`.
- `control-muefs doctor` is clean.
- Chromium without the WebMCP origin-isolation flag still serves the hub UI; the WebMCP pill may read `Unavailable`. Hub search does not require the flag.

- **Open hub.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /agent`. Heading `MUEFS Agent Hub` is visible. Headings `Case search` and `Prompts` are visible.
- **Declarative search.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser fill --label "Party name" --value Smith` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Search"`. A hit list appears (`.agent-declarative-hits`) containing a Smith-related title.
- **Open a docket.** Click a hit's `Open` link. The case docket (`.case-detail-page`) loads.
- **Proof.** Snapshot and screenshot to `artifacts/agent-hub/hub.aria.txt` and `artifacts/agent-hub/hub.png` after the search. They show `MUEFS Agent Hub` and the search hits.

`npm run smoke:webmcp` in `frontend/` runs the same checks headlessly with Playwright against `http://localhost:3000`, the origin both `run_demo.py` and the Compose stack allow (pass another base URL as its argument). Prefer `control-muefs` so evidence lands in `artifacts/`.

## Gotchas

- Hub `Party name` (`agentHubParty`) is not the portal search `Party Name` (`partyName`). Drive the hub form on `/agent`, not `/cases/search`.
- `Unavailable` WebMCP is expected in stock Chromium. Do not fail the hub proof on that pill.
- The Smith search needs seeded Smith cases; no hits means reseed (`rm backend/demo.db` then relaunch), not a selector bug.
- Sidebar Agent Hub is hidden when `webMcpStatus().available` is false. `/agent` itself still loads.
