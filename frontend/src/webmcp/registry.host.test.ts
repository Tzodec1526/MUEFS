import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { catalogForRole } from './catalog';
import type { ModelContext, ModelContextRegisterOptions, ModelContextTool } from './types';

const { searchCases } = vi.hoisted(() => ({ searchCases: vi.fn() }));
vi.mock('../api/cases', () => ({ searchCases, getCase: vi.fn() }));
vi.mock('../components/auth/LoginScreen', () => ({
  getDemoRole: () => localStorage.getItem('demo_role'),
  getDemoCourtId: () => 3,
}));

const SESSION_KEY = 'muefs_auth_session';
const FILER_TOOLS = ['list_my_filings', 'get_filing_details', 'validate_filing', 'start_motion_filing'];

/** A browser host as the spec describes it: one name map, and a registration's signal unregisters it. */
class FakeHost implements ModelContext {
  readonly tools = new Map<string, ModelContextTool>();
  /** Removed from the spec and from Chrome 147; MUEFS must not call it. */
  readonly provideContext = vi.fn();

  async registerTool(tool: ModelContextTool, { signal }: ModelContextRegisterOptions = {}) {
    if (signal?.aborted) throw signal.reason;
    if (this.tools.has(tool.name)) throw new DOMException(`Duplicate tool name: ${tool.name}`, 'InvalidStateError');
    this.tools.set(tool.name, tool);
    signal?.addEventListener('abort', () => {
      if (this.tools.get(tool.name) === tool) this.tools.delete(tool.name);
    }, { once: true });
  }

  names() { return [...this.tools.keys()]; }
}

const namesFor = (role: string | null) => catalogForRole(role).map(tool => tool.name);

/** A fresh registry and activity log, as on page load. */
async function load() {
  vi.resetModules();
  const registry = await import('./registry');
  const activity = await import('./activity');
  return { ...registry, ...activity };
}

const { location } = window;

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem(SESSION_KEY, JSON.stringify({ generation: 'first', restore: false }));
  // Each test's registry listens on its own window (axios reads the location when it loads).
  vi.stubGlobal('window', Object.assign(new EventTarget(), { location }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete document.modelContext;
  vi.restoreAllMocks();
});

describe('registration with a browser host', () => {
  it('drops the filer tools when an attorney session becomes public', async () => {
    localStorage.setItem('demo_role', 'attorney');
    const host = new FakeHost();
    document.modelContext = host;
    const { initMuefsWebMcp } = await load();
    initMuefsWebMcp();
    await vi.waitFor(() => expect(host.names()).toEqual(namesFor('attorney')));
    expect(host.names()).toEqual(expect.arrayContaining(FILER_TOOLS));

    localStorage.setItem('demo_role', 'public');
    window.dispatchEvent(new Event('muefs-demo-role-changed'));
    await vi.waitFor(() => expect(host.names()).toEqual(namesFor('public')));
    for (const name of FILER_TOOLS) expect(host.tools.has(name)).toBe(false);
    expect(host.provideContext).not.toHaveBeenCalled();
  });

  it('keeps every other tool when a form already holds one name', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    localStorage.setItem('demo_role', 'attorney');
    const host = new FakeHost();
    // A declarative form registered under an imperative name (MUEFS's forms no longer do).
    host.tools.set('search_cases', { name: 'search_cases', description: 'form', execute: vi.fn() });
    document.modelContext = host;
    const { initMuefsWebMcp } = await load();
    initMuefsWebMcp();
    await vi.waitFor(() => expect(host.names()).toHaveLength(namesFor('attorney').length));
    expect(host.names()).toEqual(expect.arrayContaining(namesFor('attorney')));
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('search_cases'), expect.any(DOMException));
  });

  it('uses navigator.modelContext in browsers that have not moved it to document', async () => {
    const host = new FakeHost();
    vi.stubGlobal('navigator', { modelContext: host });
    const { initMuefsWebMcp, webMcpStatus } = await load();
    expect(webMcpStatus().available).toBe(true);
    initMuefsWebMcp();
    await vi.waitFor(() => expect(host.names()).toEqual(namesFor(null)));
  });

  it('prefers document.modelContext, the spec location, when both exist', async () => {
    const current = new FakeHost();
    const deprecated = new FakeHost();
    document.modelContext = current;
    vi.stubGlobal('navigator', { modelContext: deprecated });
    const { initMuefsWebMcp } = await load();
    initMuefsWebMcp();
    await vi.waitFor(() => expect(current.names()).toEqual(namesFor(null)));
    expect(deprecated.names()).toEqual([]);
  });
});

describe('agent activity across sessions', () => {
  async function started(role: string) {
    localStorage.setItem('demo_role', role);
    const host = new FakeHost();
    document.modelContext = host;
    const loaded = await load();
    loaded.initMuefsWebMcp();
    await vi.waitFor(() => expect(host.names()).toEqual(namesFor(role)));
    loaded.logAgentActivity('search_cases', { party_name: 'Smith' }, true, 5);
    return { ...loaded, host };
  }

  it('clears the log when the role changes in this tab', async () => {
    const { getAgentActivity } = await started('attorney');
    localStorage.setItem('demo_role', 'clerk');
    window.dispatchEvent(new Event('muefs-demo-role-changed'));
    expect(getAgentActivity()).toEqual([]);
  });

  it('keeps the log for a court switch or profile refresh in the same session', async () => {
    const { getAgentActivity } = await started('clerk');
    localStorage.setItem('demo_court_id', '4');
    window.dispatchEvent(new Event('muefs-demo-role-changed'));
    expect(getAgentActivity()).toHaveLength(1);
  });

  it.each([
    ['signs in to another account', SESSION_KEY, () => localStorage.setItem(SESSION_KEY, '{"generation":"second"}')],
    ['switches roles', 'demo_role', () => localStorage.setItem('demo_role', 'srl')],
    ['clears storage', null, () => localStorage.clear()],
  ])('clears the log when another tab %s', async (_what, key, change) => {
    const { getAgentActivity } = await started('attorney');
    change();
    window.dispatchEvent(new StorageEvent('storage', { key }));
    expect(getAgentActivity()).toEqual([]);
  });

  it('ignores storage events that leave the session alone', async () => {
    const { getAgentActivity } = await started('attorney');
    window.dispatchEvent(new StorageEvent('storage', { key: SESSION_KEY }));
    window.dispatchEvent(new StorageEvent('storage', { key: 'demo_court_id' }));
    expect(getAgentActivity()).toHaveLength(1);
  });

  it('clears on page load a log this tab kept from another session', async () => {
    await started('attorney');
    // The tab reloads after the account changed while it was discarded (sessionStorage survives).
    localStorage.setItem(SESSION_KEY, '{"generation":"second"}');
    const reloaded = await load();
    expect(reloaded.getAgentActivity()).toHaveLength(1);
    reloaded.initMuefsWebMcp();
    expect(reloaded.getAgentActivity()).toEqual([]);
  });

  it('keeps the log across a reload in the same session', async () => {
    await started('attorney');
    const reloaded = await load();
    reloaded.initMuefsWebMcp();
    expect(reloaded.getAgentActivity()).toHaveLength(1);
  });

  it('does not log into the new session a call that was running when the old one ended', async () => {
    const { getAgentActivity, clearAgentActivity, host } = await started('public');
    clearAgentActivity();
    let finish!: (value: unknown) => void;
    searchCases.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const call = host.tools.get('search_cases')!.execute({ party_name: 'Smith' });

    localStorage.setItem('demo_role', 'attorney');
    window.dispatchEvent(new Event('muefs-demo-role-changed'));
    finish({ cases: [], total: 0, page: 1, page_size: 25 });
    expect(JSON.parse(await call as string)).toMatchObject({ ok: true });
    expect(getAgentActivity()).toEqual([]);
  });
});
