# MUEFS WebMCP — Agent Integration Guide

MUEFS is a **WebMCP Challenge** entry: a real court-filing domain where humans and AI agents collaborate through the browser — not a toy CRUD demo.

**Live (challenge):** https://webmcp.tomcedoz.com/agent  
**Canonical demo:** https://demo.tomcedoz.com/agent *(Manual Deploy latest `main` on Render to refresh)*

## Why WebMCP fits e-filing

Court filing is multi-step, rule-bound, and role-specific. Agents excel at research and checklist guidance; humans must retain submit authority. WebMCP bridges that gap:

| Before WebMCP | With MUEFS WebMCP |
|---|---|
| Agent scrapes HTML tables | `search_cases` returns structured docket JSON |
| User re-types case numbers into wizard | `research_case_for_motion` → pre-filled `/filing/new?...` URL |
| Agent guesses MCR companions | `get_motion_checklists` returns MCR 2.119 items |
| Same tools for public vs clerk | **Role-aware** registration — clerks never see filer-only tools |

## Enable WebMCP

### WebMCP-capable agent browser

1. Open the live demo URL in an agent browser that supports WebMCP
2. Confirm `/agent` shows **WebMCP status: Active**

### Chrome (local / testing)

1. Chrome **149+**
2. `chrome://flags/#enable-webmcp-testing` → **Enabled**
3. Restart Chrome
4. Vite dev server sends COOP/COEP headers for origin isolation

## Judge quick test (2 minutes)

1. Open https://webmcp.tomcedoz.com/agent (or https://demo.tomcedoz.com/agent after Manual Deploy) — confirm **WebMCP status: Active** and live activity feed
2. Ask your agent:

   > Call `get_agent_session`, then `get_agent_catalog`. Summarize available tools.

3. Attorney workflow:

   > Sign in as attorney, run `attorney_motion_workflow` for party Smith, then `navigate_to` the filing wizard path.

4. Clerk path:

   > `sign_in_demo_role` clerk → `clerk_triage_workflow` → `navigate_to` /clerk/queue

## Tool catalog (23 tools, role-filtered: 16 public · 20 filer · 19 clerk)

| Tool | Tier | Role | Description |
|---|---|---|---|
| `get_agent_catalog` | discovery | all | Discover tools for current session |
| `get_agent_session` | discovery | all | Role, path, drafts — **start here** |
| `get_agent_activity` | discovery | all | Recent tool calls (same feed as `/agent`) |
| `get_challenge_briefing` | discovery | all | Judge overview: URLs, prompts, HITL rules |
| `search_cases` | discovery | all | Public docket search (+ declarative form) |
| `get_case_docket` | discovery | all | Case detail by id |
| `list_courts` | discovery | all | E-filing enabled courts by county |
| `research_case_for_motion` | workflow | all | Search → docket → MCR checklist → wizard URL |
| `attorney_motion_workflow` | workflow | all* | Full filer plan with drafts + wizard URL |
| `clerk_triage_workflow` | workflow | all* | Queue counts + review plan |
| `explain_mcr_for_filing` | workflow | all | Plain-language MCR for SRLs |
| `get_filing_requirements` | discovery | all | Document requirements for court/case type |
| `get_motion_checklists` | discovery | all | MCR 2.119 motion companions |
| `navigate_to` | action | all | Same-origin navigation |
| `sign_in_demo_role` | action | demo | Switch attorney / clerk / srl / public |
| `open_filing_for_review` | discovery | clerk | Deep link into queue for one filing |
| `get_current_demo_role` | discovery | demo | Current session role |
| `list_my_filings` | discovery | filer | Attorney/SRL filings |
| `get_filing_details` | discovery | filer | Single filing status |
| `validate_filing` | workflow | filer | Pre-submit MCR validation |
| `start_motion_filing` | action | filer | Build wizard URL from case ids |
| `get_clerk_review_queue` | discovery | clerk | Pending review list |
| `clerk_queue_summary` | discovery | clerk | Queue aggregates |

\*Workflow tools are callable when anonymous but return `needs_sign_in` until the correct role is active.

## Live activity feed

Every tool execution is logged client-side and shown on `/agent`. Agents can re-read that feed via `get_agent_activity`. Judges can verify calls without DevTools — useful for demo videos and Devpost review.

## Architecture

```
frontend/src/webmcp/
  registry.ts          # Role-aware register + refresh on role change
  catalog.ts           # Tool metadata for /agent page (22 tools, 3 tiers)
  activity.ts          # Live execution log for /agent
  registerTool.ts      # Logging wrapper for every registerTool call
  annotations.ts       # readOnlyHint / untrustedContentHint
  output.ts            # Structured JSON + prompt-injection sanitization
  tools/
    session.ts         # get_agent_session bootstrap
    workflows.ts         # attorney_motion_workflow, clerk_triage_workflow, explain_mcr
    courts.ts          # list_courts
    orchestration.ts   # research_case_for_motion
    search.ts          # Declarative form + imperative search
    rules.ts           # MCR requirements & checklists
    auth.ts            # Demo role sign-in for judges
    ...
```

### Declarative + imperative hybrid

- **Declarative:** `CaseSearch` form uses `toolname="search_cases"` so agents can fill the same UI humans use.
- **Imperative:** Orchestration tools call the REST API for multi-step workflows agents cannot express as a single form.

### Security

- `untrustedContentHint` on docket-returning tools (party names, case titles sanitized)
- Mutating tools (`navigate_to`, `sign_in_demo_role`) use `readOnlyHint: false` and a human `confirm` gate (or `confirmed=true` after agreement)
- Optional `provideContext` publishes role/path/suggested next tool when the host supports it
- No agent-side submit — filing submission stays in the human-reviewed wizard

## Implementation reference

```typescript
await document.modelContext.registerTool({
  name: 'research_case_for_motion',
  description: '...',
  inputSchema: { type: 'object', properties: { party_name: { type: 'string' } } },
  annotations: { readOnlyHint: true, untrustedContentHint: true },
  async execute(input) {
    // search → docket → checklists → structured plan
  },
});
```

Registration: `frontend/src/main.tsx` → `initMuefsWebMcp()`.

## Challenge submission

See [WEBMCP_CHALLENGE.md](./WEBMCP_CHALLENGE.md) for Devpost copy, video script outline, and commit evidence.
