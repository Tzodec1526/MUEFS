# Agent Hub

The Agent Hub at `/agent` is a public catalog of WebMCP tools plus a declarative case search and flagship demo buttons (attorney Smith motion, clerk triage, SRL MCR).

## Sub-features

- `hub-open` shows heading `MUEFS Agent Hub` with sections WebMCP, Activity, Case search, Run, Workflows, Discovery, Prompts.
- `hub-search` runs the hub `search_cases` form (Party name, default Smith) and lists hits with `Open`.
- `hub-attorney-run` runs `Attorney · Smith motion` until `attorney_motion_workflow` appears in the step list with a non-zero required-docs line.
- `hub-open-result` shows `Open result` after a successful run.

## How to get to it (user POV)

- Open `/agent` (no account required).
- Sidebar `Agent Hub` when WebMCP is available in the browser.
- Header WebMCP link (when shown).
- Hub nav `Sign in`, `Case search`, `App home`.

## Driving it with control-muefs

Preconditions:

- MUEFS is healthy at `http://127.0.0.1:3000`.
- `control-muefs doctor` is clean.
- Chromium without the WebMCP origin-isolation flag still serves the hub UI; the WebMCP pill may read `Unavailable`. Hub search and Run buttons do not require the flag.

- **Open hub.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /agent`. Heading `MUEFS Agent Hub` is visible. Headings `Case search` and `Run` are visible.
- **Declarative search.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser fill --label "Party name" --value Smith` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Search"`. A hit list appears (`.agent-declarative-hits` in the smoke script) containing a Smith-related title.
- **Attorney flagship.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Attorney · Smith motion"`. Wait until text `attorney_motion_workflow` is visible. The detail must not be `0 required docs · 0 motion`.
- **Proof.** Snapshot and screenshot to `artifacts/agent-hub/hub.aria.txt` and `artifacts/agent-hub/hub.png` after search or after the attorney run. They show `MUEFS Agent Hub` and the search hits or workflow step.

There is also `frontend/scripts/smoke-webmcp-ui.mjs` (Playwright, default base `http://127.0.0.1:8010` — **wrong port for this demo**; pass `http://127.0.0.1:3000`). Prefer `control-muefs` so evidence lands in `artifacts/`.

## Gotchas

- Hub `Party name` (`agentHubParty`) is not the portal search `Party Name` (`partyName`). Drive the hub form on `/agent`, not `/cases/search`.
- `Unavailable` WebMCP is expected in stock Chromium. Do not fail the hub proof on that pill.
- `Attorney · Smith motion` needs seeded Smith cases and MCR requirements; a `No Smith case in demo seed` toast means reseed (`rm backend/demo.db` then relaunch), not a selector bug.
- Sidebar Agent Hub is hidden when `webMcpStatus().available` is false. `/agent` itself still loads.
