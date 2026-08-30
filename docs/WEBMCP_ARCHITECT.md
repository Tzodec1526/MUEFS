# Architect sketch: WebMCP challenge polish

## Caller's usage

```ts
navigateApp('/filing/new?case_id=1'); // SPA navigate; activity feed survives
await registerTool({ name: 'navigate_to', annotations: MUTATING, execute: async ({ path, confirmed }) => {
  if (!confirmed && !(await confirmAgentAction(`Navigate to ${path}?`))) return toolError('Human declined', 'needs_confirmation');
  return navigateApp(path);
}});
document.modelContext?.provideContext?.({ role, path, suggested_next_tool }); // feature-detect
```

## Synthesis decision

**Base: Design A (SPA bridge + sessionStorage).** Design B (reload + sessionStorage only) rejected because flagship prompts call `navigate_to` and would flash-wipe the hub UX.

## Types

```ts
// navigate.ts
export const MUEFS_NAVIGATE_EVENT = 'muefs-navigate';
export function navigateApp(path: string): { ok: true; path: string } | { ok: false; error: string };
// dispatches CustomEvent detail={path} when a React listener is armed; else location.assign fallback

// confirm.ts
export function confirmAgentAction(message: string): Promise<boolean>;

// types.ts — extend ModelContext
provideContext?(context: Record<string, unknown>): void | Promise<void>;

// context.ts
export function publishAgentPageContext(): void; // role, path, drafts hint, suggested tool
```

## Module map

- `navigate.ts` — allowlist + SPA event
- `App.tsx` or small `WebMcpNavigateBridge` — `useNavigate` listener
- `activity.ts` — sessionStorage hydrate/persist
- `confirm.ts` — window.confirm wrapper (HITL for MUTATING)
- `annotations.ts` — MUTATING used on navigate_to, sign_in_demo_role
- `registry.ts` — provideContext + addEventListener toolchange (don't clobber); late modelContext poll
- `tools/clerk.ts` — `open_filing_for_review` deep link
- `catalog.ts` + test — role matrix
- Header / WebMcpHeaderLink — always show Agent; notify on role clear

## Not implemented bodies

Fill against this contract. No new abstraction layers beyond the event bridge.
