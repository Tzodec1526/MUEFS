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
let nextId = 1;
const entries: AgentActivityEntry[] = [];

function hydrate(): void {
  if (typeof sessionStorage === 'undefined') return;
  try {
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

export function logAgentActivity(
  tool: string,
  input: Record<string, unknown>,
  ok: boolean,
  durationMs: number,
): void {
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
  persist();
}
