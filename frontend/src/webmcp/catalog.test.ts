import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearAgentActivity, getAgentActivity } from './activity';
import { catalogForBuild, catalogForRole } from './catalog';
import { TOOL_DEFINITIONS } from './definitions';
import { registerRoleTools } from './registerTools';
import { TOOL_EXECUTORS } from './tools';
import type { ModelContextRegisterOptions, ModelContextTool } from './types';

const { getDemoRole, listFilings } = vi.hoisted(() => ({
  getDemoRole: vi.fn((): string | null => null),
  listFilings: vi.fn(async () => ({ filings: [], total: 0, status_counts: {}, court_names: {} })),
}));
vi.mock('../components/auth/LoginScreen', () => ({ getDemoRole, getDemoCourtId: () => 3 }));
vi.mock('../api/filings', () => ({
  listFilings, getFiling: vi.fn(), validateFiling: vi.fn(), getClerkQueue: vi.fn(), getFilingStatusCounts: vi.fn(),
}));

const ROLES = [null, 'public', 'attorney', 'srl', 'clerk', 'admin'];

async function register(role: string | null, signal = new AbortController().signal) {
  const registerTool = vi.fn(async (_tool: ModelContextTool, _options?: ModelContextRegisterOptions) => {});
  await registerRoleTools({ registerTool }, role, signal);
  // The pass's signal is what unregisters its tools when the role changes.
  for (const [tool, options] of registerTool.mock.calls) {
    expect(options?.signal, `${tool.name} registered without the pass's signal`).toBe(signal);
  }
  return registerTool.mock.calls.map(([tool]) => tool);
}

async function execute(tool: ModelContextTool | undefined, input: Record<string, unknown> = {}) {
  return JSON.parse(await tool!.execute(input) as string);
}

it('has exactly one implementation per defined tool', () => {
  expect(Object.keys(TOOL_EXECUTORS).sort()).toEqual(TOOL_DEFINITIONS.map(t => t.name).sort());
  expect(new Set(TOOL_DEFINITIONS.map(t => t.name)).size).toBe(TOOL_DEFINITIONS.length);
});

describe.each([true, false])('demo build %s', demo => {
  beforeEach(() => {
    vi.stubEnv('VITE_ALLOW_DEMO_MODE', String(demo));
    getDemoRole.mockReset().mockReturnValue(null);
    listFilings.mockClear();
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    clearAgentActivity();
  });

  it.each(ROLES)('registers exactly the catalog shown for %s, from the same definitions', async role => {
    const registered = await register(role);
    const catalog = catalogForRole(role);

    expect(registered.map(t => t.name)).toEqual(catalog.map(t => t.name));
    registered.forEach((tool, i) => {
      const definition = TOOL_DEFINITIONS.find(d => d.name === tool.name)!;
      expect(tool).toMatchObject({
        title: definition.title,
        description: definition.description,
        inputSchema: definition.inputSchema,
        annotations: definition.annotations,
      });
      expect(catalog[i]).toEqual({
        name: definition.name,
        title: definition.title,
        description: definition.description,
        readOnly: definition.annotations.readOnlyHint === true,
        tier: definition.tier,
      });
    });

    const names = registered.map(t => t.name);
    expect(names.includes('validate_filing')).toBe(role === 'attorney' || role === 'srl');
    expect(names.includes('get_clerk_review_queue')).toBe(role === 'clerk');
    expect(names.includes('sign_in_demo_role')).toBe(demo);
    expect(names.includes('get_current_demo_role')).toBe(demo);
  });

  it('gives administrators the public tool set', () => {
    expect(catalogForRole('admin')).toEqual(catalogForRole('public'));
    expect(catalogForRole('admin')).toEqual(catalogForRole(null));
  });

  it('has the per-role counts documented in docs/WEBMCP.md', () => {
    const counts = Object.fromEntries(ROLES.map(role => [String(role), catalogForRole(role).length]));
    expect({ build: catalogForBuild().length, ...counts }).toEqual(demo
      ? { build: 19, null: 14, public: 14, attorney: 18, srl: 18, clerk: 15, admin: 14 }
      : { build: 17, null: 12, public: 12, attorney: 16, srl: 16, clerk: 13, admin: 12 });
  });

  it.each(ROLES)('get_agent_catalog lists what was registered for %s', async role => {
    const registered = await register(role);
    const result = await execute(registered.find(t => t.name === 'get_agent_catalog'));
    expect(result.tools.map((t: { name: string }) => t.name)).toEqual(registered.map(t => t.name));
    expect(result.tool_count).toBe(registered.length);
    expect(getAgentActivity()[0]).toMatchObject({ tool: 'get_agent_catalog', ok: true });
  });

  it.each([['admin', 'list_my_filings'], ['clerk', 'list_my_filings'], ['attorney', 'get_clerk_review_queue']])(
    'refuses a %s session a stale %s registration', async (current, name) => {
      const registered = await register(name === 'list_my_filings' ? 'attorney' : 'clerk');
      getDemoRole.mockReturnValue(current);
      const result = await execute(registered.find(t => t.name === name));
      expect(result).toMatchObject({ ok: false, code: 'needs_sign_in' });
      expect(result.error.includes('sign_in_demo_role')).toBe(demo);
      expect(listFilings).not.toHaveBeenCalled();
    },
  );

  it('runs a filer tool for a filer session', async () => {
    const registered = await register('srl');
    getDemoRole.mockReturnValue('srl');
    expect(await execute(registered.find(t => t.name === 'list_my_filings'))).toMatchObject({ ok: true, total: 0 });
    expect(listFilings).toHaveBeenCalledOnce();
  });
});

it('stops registering once a newer pass aborts this one', async () => {
  const controller = new AbortController();
  const registerTool = vi.fn(async () => {
    if (registerTool.mock.calls.length === 3) controller.abort();
  });
  await registerRoleTools({ registerTool }, 'attorney', controller.signal);
  expect(registerTool).toHaveBeenCalledTimes(3);
});

it("registers every tool with the pass's AbortSignal", async () => {
  const controller = new AbortController();
  const registerTool = vi.fn(async (_tool: ModelContextTool, _options?: ModelContextRegisterOptions) => {});
  await registerRoleTools({ registerTool }, 'attorney', controller.signal);
  expect(registerTool).toHaveBeenCalledTimes(catalogForRole('attorney').length);
  for (const [, options] of registerTool.mock.calls) expect(options).toEqual({ signal: controller.signal });
});

it('registers the other tools when the host rejects one', async () => {
  // Chrome rejects a name the page already uses, for example a declarative form's.
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  const registered: string[] = [];
  const registerTool = vi.fn(async (tool: ModelContextTool) => {
    if (tool.name === 'search_cases') throw new DOMException('Duplicate tool name', 'InvalidStateError');
    registered.push(tool.name);
  });
  await registerRoleTools({ registerTool }, 'attorney', new AbortController().signal);
  expect(registered).toEqual(catalogForRole('attorney').map(t => t.name).filter(name => name !== 'search_cases'));
  expect(warn).toHaveBeenCalledOnce();
  expect(String(warn.mock.calls[0][0])).toContain('search_cases');
  warn.mockRestore();
});

it('stops without complaint when its own pass is aborted mid-registration', async () => {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  const controller = new AbortController();
  // The spec: an aborted signal rejects registerTool with the abort reason.
  const registerTool = vi.fn(async () => {
    if (registerTool.mock.calls.length === 2) {
      controller.abort();
      throw controller.signal.reason;
    }
  });
  await registerRoleTools({ registerTool }, 'attorney', controller.signal);
  expect(registerTool).toHaveBeenCalledTimes(2);
  expect(warn).not.toHaveBeenCalled();
  warn.mockRestore();
});
