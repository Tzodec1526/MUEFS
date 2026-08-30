# Devpost paste fields (WebMCP Challenge)

Copy into https://webmcp.devpost.com/ before **Sep 3, 2026 @ 1:00 PM PT**.

## Project name

MUEFS — Agent-native Michigan court e-filing

## Tagline (≤ one line)

Statewide e-filing where agents research dockets and MCR checklists; humans keep submit authority.

## Live demo URL

**Working now:** https://webmcp.tomcedoz.com/agent  
(also https://muefs.tomcedoz.com/agent · https://muefs-webmcp-live.tom-72b.workers.dev/agent)

**Canonical after Manual Deploy:** https://demo.tomcedoz.com/agent

*(Operator: Manual Deploy latest `main` on Render `muefs-demo` — `autoDeploy` is off. Or add secret `RENDER_DEPLOY_HOOK_URL` and run Actions → "Deploy demo (Render hook)". Interim front doors depend on the local Docker tunnel until Render is live.)*

## Demo video URL

*(Upload `demo/muefs-webmcp-challenge.mp4` or a live agent capture with audio; paste YouTube URL here.)*

## Repository URL

https://github.com/Tzodec1526/MUEFS

License: **AGPL-3.0** (visible in GitHub About)

## Built with

WebMCP, React, FastAPI, Michigan Court Rules (MCR), Keycloak (optional), Render, Docker, TypeScript

## Text description (paste)

### Product

23 role-aware WebMCP tools (16 / 20 / 19), `/agent` hub + `get_agent_activity` / `get_challenge_briefing`, confirm on mutating tools, declarative forms (`search_cases`, `sign_in_demo_role`, clerk queue).

### Flows

- Attorney: `attorney_motion_workflow` → search → docket → requirements → wizard URL; human Submit
- Clerk: `clerk_triage_workflow`
- SRL: `explain_mcr_for_filing`

### Implementation

- Imperative: `document.modelContext.registerTool()` in `frontend/src/webmcp/` (23 tools)
- Declarative: `toolname` on case search, login, clerk queue, hub search
- Role-aware re-registration; optional `provideContext` on SPA routes
- `untrustedContentHint` + sanitized docket text

### Devpost criteria map

| Criterion | Where |
|---|---|
| **WebMCP Leverage** | Imperative + declarative; `provideContext`; activity feed |
| **Execution** | Live `/agent`, role catalog, HITL, seeded Smith / CIV-GEN |
| **Potential Impact** | Agents research/navigate; humans Submit; attorney/clerk/SRL |
| **Creativity** | MCR companions as tools; workflows; same UI for humans and agents |

## Testing instructions

1. Open the live URL with WebMCP enabled (or Chrome with `#enable-webmcp-testing`).
2. Visit `/agent` — status **Active**, tool count **16 / 20 / 19** by role; try declarative search + Flagship buttons; activity feed updates on tool calls.
3. Prompt: `Call get_challenge_briefing, then get_agent_session and get_agent_catalog.`
4. Prompt: `Sign in as attorney, run attorney_motion_workflow for party Smith, then get_agent_activity.`
5. Optional: clerk / SRL prompts on the hub, or click Flagship demo buttons without a live agent.

No credentials required for demo roles. Optional hosted `DEMO_MODE_SECRET` is in `/config.js` when enabled.
