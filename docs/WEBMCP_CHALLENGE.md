# WebMCP Challenge — Submission Draft

Use this for [Devpost](https://webmcp.devpost.com/) (deadline **Sep 3, 2026 @ 1:00 PM PT**).

## Project title

**MUEFS — Agent-native Michigan court e-filing**

## One-line pitch

The statewide Michigan e-filing portal where AI agents research dockets, load MCR motion checklists, and pre-fill filing wizards — while humans keep submit authority.

## Why WebMCP is the right fit

Court filing combines public records research, role-based access (public / filer / clerk), and Michigan Court Rules companions (MCR 2.119 briefs, proposed orders). Before WebMCP, agents either scraped HTML or hallucinated requirements. MUEFS exposes a **23-tool catalog**, role-filtered to **16 / 20 / 19** tools (public / filer / clerk), a **live activity feed** on `/agent` (also readable via `get_agent_activity`), SPA-safe navigation with human confirmation on mutating tools, plus **declarative** forms on the hub, case search, login, and clerk queue so agents and litigants share one interface.

**Together, humans and agents can:**

1. Search `Smith` on the public docket, pull motion checklists, and open a pre-filled motion wizard in one `research_case_for_motion` call.
2. Validate a draft filing against MCR required documents before the human clicks Submit.
3. Let clerks triage queues via `clerk_queue_summary` without exposing filer credentials.

## How we implemented WebMCP

- **Imperative tools** via `document.modelContext.registerTool()` in `frontend/src/webmcp/`
- **Declarative tools** on case search and login forms (`toolname="search_cases"`, `sign_in_demo_role`)
- **Role-aware registry** re-registers tools when demo role changes (attorney unlocks filer tools; clerk unlocks queue tools)
- **Agent hub** at `/agent` with judge prompts, workflow cards, live activity feed, and browser `getTools()` count
- **Workflow tier** — `attorney_motion_workflow`, `clerk_triage_workflow`, `explain_mcr_for_filing`
- **Output hardening** — `untrustedContentHint` + sanitized docket text per WebMCP security guidance

## Live URL

**Working now:** https://webmcp.tomcedoz.com  
Agent hub: https://webmcp.tomcedoz.com/agent

**After Manual Deploy:** https://demo.tomcedoz.com/agent

## Testing instructions for judges

1. Open the URL in **ChatGPT in-app browser** (WebMCP on) or Chrome with `#enable-webmcp-testing`.
2. Visit `/agent` — status should show **Active** with ~14–20 tools (depends on role); activity feed updates on each tool call.
3. Prompt: *"Call get_agent_session and get_agent_catalog."*
4. Prompt: *"Sign in as attorney, run attorney_motion_workflow for party Smith, navigate to the wizard."*
5. Optional clerk: *"Sign in as clerk and run clerk_triage_workflow."*
6. Optional SRL: *"Sign in as srl and run explain_mcr_for_filing for court 3 case type 35 motion."*

No credentials required — demo uses role picker + optional `DEMO_MODE_SECRET` on hosted deploy.

## Repository

https://github.com/Tzodec1526/MUEFS (AGPL-3.0 — GitHub license badge)

**WebMCP work during challenge period:** commits on `main` after Aug 25 adding `frontend/src/webmcp/`, `/agent` hub, orchestration tools, and `docs/WEBMCP.md`. Topics: `webmcp`, `openai-challenge`, `court-filing`.

## Operator go-live (when you are ready)

`render.yaml` has `autoDeploy: false`. WebMCP is on `main` but `demo.tomcedoz.com` stays on the old build until you deploy manually.

1. In Render → `muefs-demo` → **Manual Deploy** → deploy latest `main`.
2. Confirm https://demo.tomcedoz.com/agent shows Agent Hub + Flagship demos.
3. Confirm role switch works (demo secret via `/config.js`).
4. Optional preflight (no Render): `docker build -t muefs-demo:webmcp .` then `powershell -File scripts/verify-webmcp-image.ps1`
5. Record the YouTube video with audio using the voiceover script above (ChatGPT path preferred; Flagship buttons as B-roll).
6. Optional: set `autoDeploy: true` again after the challenge build is frozen.
7. Submit on Devpost before Sep 3, 2026 @ 1:00 PM PT.

## Demo video outline (< 3 min)

**Required:** public YouTube with **audio** explaining what you built and how WebMCP is used. Silent slideshows fail the gate.

### Voiceover script (read aloud)

1. *(0:00)* "Michigan e-filing is fragmented. Motions under MCR 2.119 need briefs, proposed orders, and proof of service. Agents used to scrape HTML or invent requirements."
2. *(0:20)* Open https://demo.tomcedoz.com/agent. "This is the MUEFS Agent Hub. WebMCP exposes a role-aware tool catalog — fifteen to nineteen tools depending on sign-in — so ChatGPT works the same portal a human attorney uses."
3. *(0:40)* In ChatGPT in-app browser, paste the attorney flagship prompt. Show activity feed filling. "One call runs search, docket, MCR checklist, and a pre-filled wizard URL. The human still clicks Submit."
4. *(1:15)* Open the wizard from the result. "Human in the loop by design. Agents research and navigate. They never file."
5. *(1:35)* Clerk prompt: triage workflow then queue. "Same site, different tool set when you sign in as clerk."
6. *(1:55)* Case search form with toolname search_cases. "Declarative WebMCP. The agent fills the form humans already use."
7. *(2:15)* Show GitHub AGPL repo and the Run attorney_motion_workflow button on /agent for backup B-roll without ChatGPT.
8. *(2:40)* "MUEFS: agent-native Michigan court e-filing. Live at demo.tomcedoz.com."

### Shot list

| Time | Shot |
|---|---|
| 0:00 | Problem: fragmented MiFILE, complex MCR motions |
| 0:20 | `/agent` — WebMCP status, tool count, activity feed |
| 0:40 | ChatGPT: flagship attorney prompt |
| 1:15 | Pre-filled wizard (human submit only) |
| 1:35 | Clerk triage |
| 1:55 | Declarative case search |
| 2:15 | Repo + Flagship demo button on `/agent` |
| 2:40 | CTA |

Record with screen capture + mic using `demo/webmcp-voiceover.txt`. Draft with audio (TTS over B-roll, replace with live ChatGPT capture before submit): `demo/muefs-webmcp-challenge.mp4`. Silent B-roll only: `demo/muefs-webmcp-challenge-broll.mp4` via `scripts/record-webmcp-demo.ps1`.

## Differentiators vs typical hackathon entries

- **Real domain depth** — MCR rules, sealed cases, clerk queue, not ecommerce
- **Human-in-the-loop by design** — agents never submit filings
- **Production-shaped** — same codebase as security-hardened court POC
- **Dual API** — declarative forms + imperative orchestration
