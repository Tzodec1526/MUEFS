# Devpost paste fields (WebMCP Challenge)

Copy into https://webmcp.devpost.com/ before **Sep 3, 2026 @ 1:00 PM PT**.

## Project name

MUEFS — Agent-native Michigan court e-filing

## Tagline (≤ one line)

Statewide e-filing where agents research dockets and MCR checklists; humans keep submit authority.

## Live demo URL

**Working now:** https://webmcp.tomcedoz.com/agent  
(also https://muefs-webmcp-live.tom-72b.workers.dev/agent)

**Canonical after Manual Deploy:** https://demo.tomcedoz.com/agent

*(Operator: Manual Deploy latest `main` on Render `muefs-demo` — `autoDeploy` is off. Or add secret `RENDER_DEPLOY_HOOK_URL` and run Actions → "Deploy demo (Render hook)". The webmcp.* front door depends on the local Docker tunnel until Render is live.)*

## Demo video URL

*(Upload `demo/muefs-webmcp-challenge.mp4` or a live ChatGPT capture with audio; paste YouTube URL here.)*

## Repository URL

https://github.com/Tzodec1526/MUEFS

License: **AGPL-3.0** (visible in GitHub About)

## Built with

WebMCP, React, FastAPI, Michigan Court Rules (MCR), Keycloak (optional), Render, Docker, TypeScript

## Text description (paste)

### Why WebMCP fits

Court e-filing mixes public docket research, role-based access (public / filer / clerk), and Michigan Court Rules companions (MCR 2.119 briefs, proposed orders, proof of service). Before WebMCP, agents scraped HTML or invented requirements. MUEFS exposes **role-aware WebMCP tools** (discovery / workflow / action), a live **/agent** hub with activity feed, SPA-safe navigation, human confirmation on mutating tools, and **declarative** forms (`search_cases`, `sign_in_demo_role`, clerk queue filter) so agents and litigants share one interface.

### Better UX for people + agents

Attorneys ask ChatGPT to research a party and plan a motion; the agent runs `attorney_motion_workflow` (search → docket → requirements → draft count → pre-filled wizard URL) while the human stays on the Submit button. Clerks triage queues via `clerk_triage_workflow` without filer credentials. SRLs get plain-language MCR explanations via `explain_mcr_for_filing`. Judges see every tool call on the `/agent` activity feed; agents can re-read that feed with `get_agent_activity`.

### What was difficult or impossible before

Reliable multi-step Michigan filing prep without scrapers or hallucinated MCR checklists — in the same portal a human attorney already uses, with sealed-case and role boundaries enforced.

### How we implemented WebMCP

- Imperative: `document.modelContext.registerTool()` in `frontend/src/webmcp/` (~22 tools)
- Declarative: `toolname` on case search, login, and clerk queue filter
- Role-aware re-registration when demo role changes
- Optional `provideContext` for page/session hints
- Output hardening: `untrustedContentHint` + sanitized docket text

## Testing instructions for judges

1. Open the live URL in **ChatGPT in-app browser** (WebMCP on) or Chrome with `#enable-webmcp-testing`.
2. Visit `/agent` — status **Active**, tool count **15 / 19 / 18** by role (public / filer / clerk); activity feed updates on tool calls. Try the declarative search form on the hub.
3. Prompt: `Call get_agent_session and get_agent_catalog.`
4. Prompt: `Sign in as attorney, run attorney_motion_workflow for party Smith, then get_agent_activity.`
5. Optional: clerk / SRL prompts on the hub, or click Flagship demo buttons without ChatGPT.

No credentials required for demo roles. Optional hosted `DEMO_MODE_SECRET` is in `/config.js` when enabled.
