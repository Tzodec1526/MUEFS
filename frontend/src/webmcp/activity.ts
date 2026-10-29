/** Agent tool execution log — visible on /agent. */

export interface AgentActivityEntry {
  id: number;
  tool: string;
  at: string;
  ok: boolean;
  durationMs: number;
  summary: string;
}

const MAX_ENTRIES = 40;
const STORAGE_KEY = 'muefs-agent-activity';
/** The session the stored entries were recorded under (see bindAgentActivity). */
const OWNER_KEY = 'muefs-agent-activity-owner';
let nextId = 1;
const entries: AgentActivityEntry[] = [];
let owner: string | null = null;
/** Counts clears, so a call that started before one is not logged after it. */
let epoch = 0;

function hydrate(): void {
  if (typeof sessionStorage === 'undefined') return;
  try {
    owner = sessionStorage.getItem(OWNER_KEY);
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as AgentActivityEntry[];
    if (!Array.isArray(parsed)) return;
    entries.length = 0;
    for (const e of parsed.slice(0, MAX_ENTRIES)) {
      entries.push(e);
      if (e.id >= nextId) nextId = e.id + 1;
    }
  } catch {
    /* ignore corrupt cache */
  }
}

function persist(): void {
  if (typeof sessionStorage === 'undefined') return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    if (owner === null) sessionStorage.removeItem(OWNER_KEY);
    else sessionStorage.setItem(OWNER_KEY, owner);
  } catch {
    /* quota */
  }
}

if (typeof sessionStorage !== 'undefined') {
  hydrate();
}

function summarizeInput(name: string, input: Record<string, unknown>): string {
  const keys = Object.keys(input).filter((k) => input[k] != null && input[k] !== '');
  if (!keys.length) return name;
  const preview = keys
    .slice(0, 3)
    .map((k) => `${k}=${String(input[k]).slice(0, 40)}`)
    .join(', ');
  return `${name} (${preview})`;
}

/** Pass to logAgentActivity as `since` when a call starts; see there. */
export function agentActivityEpoch(): number {
  return epoch;
}

/**
 * Record a finished tool call. With `since` (agentActivityEpoch() when the call started), a
 * call that began before the log was last cleared, for example by a sign-out or role switch,
 * is not recorded: it belongs to the session that ended.
 */
export function logAgentActivity(
  tool: string,
  input: Record<string, unknown>,
  ok: boolean,
  durationMs: number,
  since?: number,
): void {
  if (since !== undefined && since !== epoch) return;
  const entry: AgentActivityEntry = {
    id: nextId++,
    tool,
    at: new Date().toISOString(),
    ok,
    durationMs,
    summary: summarizeInput(tool, input),
  };
  entries.unshift(entry);
  if (entries.length > MAX_ENTRIES) entries.pop();
  persist();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('muefs-agent-activity', { detail: entry }));
  }
}

export function getAgentActivity(): AgentActivityEntry[] {
  return [...entries];
}

export function clearAgentActivity(): void {
  entries.length = 0;
  epoch++;
  persist();
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('muefs-agent-activity'));
}

/**
 * Keep the log to one signed-in session. `session` identifies the current session and role;
 * when it differs from the one the entries were recorded under, the log is cleared. The
 * registry calls this at start-up (the session may have changed while this tab was
 * discarded) and whenever the session or role changes, in this tab or another.
 */
export function bindAgentActivity(session: string): void {
  if (session === owner) return;
  owner = session;
  clearAgentActivity();
}
