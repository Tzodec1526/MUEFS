# WebMCP Challenge — Submission Draft

Use this for [Devpost](https://webmcp.devpost.com/) (deadline **Sep 3, 2026 @ 1:00 PM PT**).

## Project title

**MUEFS — Agent-native Michigan court e-filing**

## One-line pitch

The first statewide e-filing portal where AI agents research dockets, load MCR motion checklists, and pre-fill filing wizards — while humans keep submit authority.

## Why WebMCP is the right fit

Court filing combines public records research, role-based access (public / filer / clerk), and Michigan Court Rules companions (MCR 2.119 briefs, proposed orders). Before WebMCP, agents either scraped HTML or hallucinated requirements. MUEFS exposes **21 role-aware tools** (discovery / workflow / action tiers), a **live activity feed** on `/agent`, SPA-safe navigation with human confirmation on mutating tools, plus **declarative** case-search and sign-in forms so agents and litigants share one interface.

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

https://demo.tomcedoz.com  
Agent hub: https://demo.tomcedoz.com/agent

## Testing instructions for judges

1. Open the URL in **ChatGPT in-app browser** (WebMCP on) or Chrome with `#enable-webmcp-testing`.
2. Visit `/agent` — status should show **Active** with ~14–20 tools (depends on role); activity feed updates on each tool call.
3. Prompt: *"Call get_agent_session and get_agent_catalog."*
4. Prompt: *"Sign in as attorney, run attorney_motion_workflow for party Smith, navigate to the wizard."*
5. Optional clerk: *"Sign in as clerk and run clerk_triage_workflow."*
6. Optional SRL: *"Sign in as srl and run explain_mcr_for_filing for court 3 case type 1 motion."*

No credentials required — demo uses role picker + optional `DEMO_MODE_SECRET` on hosted deploy.

## Repository

https://github.com/Tzodec1526/MUEFS (AGPL-3.0)

**WebMCP work during challenge period:** commits on `main` adding `frontend/src/webmcp/`, `/agent` hub, orchestration tools, and `docs/WEBMCP.md`.

## Demo video outline (< 3 min)

| Time | Shot |
|---|---|
| 0:00 | Problem: fragmented MiFILE, complex MCR motions |
| 0:15 | `/agent` — WebMCP active, 20 tools, live activity feed |
| 0:35 | ChatGPT: `get_agent_session` → `attorney_motion_workflow` → wizard URL |
| 1:05 | Human navigates pre-filled wizard; agent calls `validate_filing` |
| 1:30 | Clerk: `clerk_triage_workflow` + queue UI |
| 1:50 | SRL: `explain_mcr_for_filing` plain language |
| 2:10 | Declarative forms: case search + login role picker |
| 2:30 | Architecture + AGPL open source |
| 2:45 | Call to action: unified Michigan e-filing |

Record with `scripts/record-webmcp-demo.ps1` (browser-use) or screen capture; upload to YouTube unlisted/public.

## Differentiators vs typical hackathon entries

- **Real domain depth** — MCR rules, sealed cases, clerk queue, not ecommerce
- **Human-in-the-loop by design** — agents never submit filings
- **Production-shaped** — same codebase as security-hardened court POC
- **Dual API** — declarative forms + imperative orchestration
