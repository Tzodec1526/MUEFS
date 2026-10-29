# MUEFS WebMCP

Browser tools for Michigan e-filing: agents research and navigate; humans submit.

**Hosted demo:** https://demo.tomcedoz.com/agent

## Local Chrome (dev)

1. Chrome **150+**, which has `document.modelContext`, the
   [spec's](https://webmachinelearning.github.io/webmcp/) location. Chrome 148 and 149 have
   only the older `navigator.modelContext`; MUEFS falls back to it there.
2. `chrome://flags/#enable-webmcp-testing` → **Enabled**
3. Restart Chrome
4. Vite sends COOP/COEP for origin isolation (`frontend/vite.config.ts`)

## Quick test

1. Open `/agent` — confirm WebMCP registered and activity feed
2. Call `get_agent_session`, then `get_agent_catalog`
3. Attorney: `sign_in_demo_role` attorney → `attorney_motion_workflow` party Smith → choose a case if prompted → call again with its case_id → `navigate_to` wizard path
4. Clerk: `sign_in_demo_role` clerk → `clerk_triage_workflow` → `navigate_to` /clerk/queue

Builds without demo sign-in have no `sign_in_demo_role`: sign in at `/login` yourself, and
`get_agent_session` suggests the next tool for that role.

## Tool catalog (19 in demo builds · 17 without demo sign-in)

| Session role | Demo build | Without demo sign-in |
|---|---|---|
| Anonymous, `public`, `admin` | 14 | 12 |
| Filer (`attorney`, `srl`) | 18 | 16 |
| Clerk (`clerk`) | 15 | 13 |

| Tool | Tier | Role | Description |
|---|---|---|---|
| `get_agent_catalog` | discovery | all | Tools for current session, workflows, example prompts |
| `get_agent_session` | discovery | all | Role, path, drafts, suggested next step — start here |
| `get_agent_activity` | discovery | all | Recent tool calls (same feed as `/agent`) |
| `search_cases` | discovery | all | Public docket search |
| `get_case_docket` | discovery | all | Case detail by id |
| `list_courts` | discovery | all | E-filing enabled courts by county |
| `attorney_motion_workflow` | workflow | all* | Full filer plan with drafts + wizard URL |
| `clerk_triage_workflow` | workflow | all* | Queue counts + review plan |
| `explain_mcr_for_filing` | workflow | all | Plain-language MCR for SRLs |
| `get_filing_requirements` | discovery | all | Document requirements for court/case type |
| `get_motion_checklists` | discovery | all | MCR 2.119 motion companions |
| `navigate_to` | action | all | Same-origin navigation |
| `sign_in_demo_role` | action | demo | Switch attorney / clerk / srl / public / admin |
| `get_current_demo_role` | discovery | demo | Current session role |
| `list_my_filings` | discovery | filer | Attorney/SRL filings |
| `get_filing_details` | discovery | filer | Status, documents, fee waiver request and decision |
| `validate_filing` | workflow | filer | Pre-submit MCR validation |
| `start_motion_filing` | discovery | filer | Build wizard URL from case ids |
| `get_clerk_review_queue` | discovery | clerk | Pending review list |

\*Workflow tools are registered for every role but return the `needs_sign_in` error until the
correct role is active. Its `action` names `sign_in_demo_role` in demo builds and asks the
human to sign in at `/login` otherwise.

### Declarative forms

Two forms are also declarative tools. Their names differ from every tool above: Chrome keeps
one tool name map per document, so a form holding `search_cases` would make the imperative
`search_cases` fail to register.

| Form tool | Where | Role |
|---|---|---|
| `search_cases_form` | `/cases/search`, `/agent` | all |
| `review_queue_form` | `/clerk/queue` | clerk |

The search forms answer an agent's submission through `SubmitEvent.respondWith()` (when the
browser has it) with the same JSON `search_cases` returns, or with an error result. Every
submission starts exactly one search, even one that repeats the search already shown.

If the browser rejects one tool (a name already taken, for example), MUEFS logs a console
warning and registers the rest.

### Roles and access

Each tool is defined once in `frontend/src/webmcp/definitions.ts`: name, title, description,
input schema, annotations, tier, `audience` (`everyone`, `filer` or `clerk`) and `demoOnly`.
Registration, the `/agent` page, `get_agent_catalog`, an execution-time role check and the
input check all read those definitions, so what an agent can call always matches what the
catalog shows.

**Administrators get the public tool set.** The admin console has no agent tools, and the
filing wizard and My Filings routes are closed to administrators, so filer and clerk tools are
neither registered for `admin` nor runnable by it. If the role changes before the browser drops
a registration, filer and clerk tools refuse to run and return `needs_sign_in`.

## Results and errors

Every tool returns a JSON string: `{"ok": true, ...}` on success, and on failure
`{"ok": false, "code": ..., "error": "<message>"}`, plus `status` (the HTTP status) for API
failures and `action` or `path` where the human must act first.

| Code | Meaning |
|---|---|
| `invalid` | Input outside the tool's schema, or another 4xx from the API |
| `forbidden` | API 403: this session may not see the record (sealed cases, for example) |
| `not_found` | API 404 |
| `needs_sign_in` | API 401, an expired sign-in, or a tool the session's role may not use |
| `unavailable` | Network failure, API 5xx or 429, or the signed-in account changed mid-call: retry later |
| `needs_confirmation` | The human declined a navigation or role switch |
| `needs_court_assignment` | A clerk must choose a working court at `/clerk/queue` first |
| `cancelled` | A newer search, or leaving the page, ended a search form submission before it finished |

Input is checked against the tool's input schema before anything is sent. Ids (case, filing,
court, case type) must be JSON integers from 1 to 2147483647, so agent input can never change
which API path a tool requests.

**Record text is untrusted.** Captions, party names, filing descriptions and document titles
can come from other parties. Tools returning them carry `untrustedContentHint`, and the text is
normalized first: control and format characters (zero-width characters, bidi controls,
Unicode tag characters) become spaces and other invisible code points are removed, since the
UI shows none of them.

**Case dates.** `filing_date` is the court's filing date. Until the court calendar sets it, it
is null and `stored_date_not_calendar_verified` carries the stored timestamp, which the UI
labels "Stored date (not calendar-verified)" and which is not the filing date.

## Activity feed

Tool executions log client-side on `/agent`. Agents re-read via `get_agent_activity`.

The declarative forms appear in the feed, as `search_cases_form` or `review_queue_form`, only
when the browser marks the submission as agent-invoked (`SubmitEvent.agentInvoked`, from the
[WebMCP declarative API explainer](https://github.com/webmachinelearning/webmcp/blob/main/declarative-api-explainer.md)).
Each answers the agent through `SubmitEvent.respondWith()` with the same result as
`search_cases` or `get_clerk_review_queue`. The logged duration runs from that submission
until the search it started settles; a submission whose search another search replaced is
logged as failed. Human searches never enter the feed.

The feed belongs to one signed-in session. Signing in or out, or switching roles, in this tab
or another, clears it, and a call still running at that moment is not logged afterwards.

## Architecture

```
frontend/src/webmcp/
  definitions.ts       # Every tool, defined once (metadata, schema, audience, demoOnly)
  catalog.ts           # Per-role and per-build views of the definitions
  registerTools.ts     # Registers a role's tools; role and input checks, API error results
  registry.ts          # Role-aware register + refresh on role change; binds the feed to the session
  input.ts             # Checks agent input against a tool's schema
  records.ts           # Case search results and dates as agents see them
  guidance.ts          # Next-step suggestions, sign-in hints, example prompts
  declarative.ts       # Agent-invoked declarative form submissions and their answers
  activity.ts          # Execution log for /agent
  registerTool.ts      # Logging wrapper
  annotations.ts       # readOnlyHint / untrustedContentHint
  output.ts            # Structured JSON, error codes, sanitization
  tools/
    index.ts           # One implementation per definition
    session.ts         # get_agent_catalog / get_agent_session / get_agent_activity
    workflows.ts       # attorney / clerk / explain_mcr
    courts.ts
    search.ts
    rules.ts
    auth.ts
    ...
```

- **Declarative:** `search_cases_form` and `review_queue_form` share the human UI
- **Imperative:** multi-step workflows via `document.modelContext.registerTool`, each tool
  registered with the pass's `AbortSignal` so a role change unregisters it
- **Page context:** `get_agent_session` returns the role, path and suggested next step. MUEFS
  does not call `provideContext()`, which the spec removed in March 2026.
- **HITL:** mutating tools always ask the human in the browser (an agent cannot answer for
  them); filing Submit stays human-only
- Registration: `frontend/src/main.tsx` → `initMuefsWebMcp()`
- `frontend/src/webmcp/catalog.test.ts` checks the registered tools against the catalog for
  every role in demo and non-demo builds, and pins the counts above
