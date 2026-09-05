# MUEFS WebMCP

Browser tools for Michigan e-filing: agents research and navigate; humans submit.

**Live:** https://webmcp.tomcedoz.com/agent  
**Canonical demo:** https://demo.tomcedoz.com/agent

## Local Chrome (dev)

1. Chrome **149+**
2. `chrome://flags/#enable-webmcp-testing` → **Enabled**
3. Restart Chrome
4. Vite sends COOP/COEP for origin isolation (`frontend/vite.config.ts`)

## Quick test

1. Open `/agent` — confirm WebMCP registered and activity feed
2. Call `get_agent_session`, then `get_agent_catalog`
3. Attorney: `sign_in_demo_role` attorney → `attorney_motion_workflow` party Smith → choose a case if prompted → call again with its case_id → `navigate_to` wizard path
4. Clerk: `sign_in_demo_role` clerk → `clerk_triage_workflow` → `navigate_to` /clerk/queue

## Tool catalog (20 · role-filtered 15 / 19 / 16)

| Tool | Tier | Role | Description |
|---|---|---|---|
| `get_agent_catalog` | discovery | all | Tools for current session |
| `get_agent_session` | discovery | all | Role, path, drafts — start here |
| `get_agent_activity` | discovery | all | Recent tool calls (same feed as `/agent`) |
| `get_challenge_briefing` | discovery | all | URLs, tool counts, example prompts |
| `search_cases` | discovery | all | Public docket search (+ declarative form) |
| `get_case_docket` | discovery | all | Case detail by id |
| `list_courts` | discovery | all | E-filing enabled courts by county |
| `attorney_motion_workflow` | workflow | all* | Full filer plan with drafts + wizard URL |
| `clerk_triage_workflow` | workflow | all* | Queue counts + review plan |
| `explain_mcr_for_filing` | workflow | all | Plain-language MCR for SRLs |
| `get_filing_requirements` | discovery | all | Document requirements for court/case type |
| `get_motion_checklists` | discovery | all | MCR 2.119 motion companions |
| `navigate_to` | action | all | Same-origin navigation |
| `sign_in_demo_role` | action | demo | Switch attorney / clerk / srl / public |
| `get_current_demo_role` | discovery | demo | Current session role |
| `list_my_filings` | discovery | filer | Attorney/SRL filings |
| `get_filing_details` | discovery | filer | Single filing status |
| `validate_filing` | workflow | filer | Pre-submit MCR validation |
| `start_motion_filing` | action | filer | Build wizard URL from case ids |
| `get_clerk_review_queue` | discovery | clerk | Pending review list |

\*Workflow tools are callable when anonymous but return `needs_sign_in` until the correct role is active.

## Activity feed

Tool executions log client-side on `/agent`. Agents re-read via `get_agent_activity`.

## Architecture

```
frontend/src/webmcp/
  registry.ts          # Role-aware register + refresh on role change
  catalog.ts           # Tool metadata for /agent
  activity.ts          # Execution log for /agent
  registerTool.ts      # Logging wrapper
  annotations.ts       # readOnlyHint / untrustedContentHint
  output.ts            # Structured JSON + sanitization
  tools/
    session.ts         # get_agent_session / briefing
    workflows.ts       # attorney / clerk / explain_mcr
    courts.ts
    search.ts
    rules.ts
    auth.ts
    ...
```

- **Declarative:** forms with `toolname="search_cases"` (and related) share the human UI
- **Imperative:** multi-step workflows via `document.modelContext.registerTool`
- **HITL:** mutating tools confirm; filing Submit stays human-only
- Registration: `frontend/src/main.tsx` → `initMuefsWebMcp()`
