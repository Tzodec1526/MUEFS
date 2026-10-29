import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { navigateApp } from '../navigate';
import { authTools } from './auth';
import { navigationTools } from './navigation';

vi.mock('../navigate', async (original) => ({
  ...await original<typeof import('../navigate')>(),
  navigateApp: vi.fn(() => ({ ok: true, path: '/cases/search' })),
}));
vi.mock('../../config/demoMode', () => ({ isDemoBuild: () => true }));
vi.mock('../../components/auth/LoginScreen', () => ({ getDemoRole: () => 'attorney' }));

const tools = { ...navigationTools, ...authTools };
const confirm = vi.fn();

beforeEach(() => {
  vi.mocked(navigateApp).mockClear();
  confirm.mockReset();
  vi.stubGlobal('window', { confirm });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function run(name: 'navigate_to' | 'sign_in_demo_role', input: Record<string, unknown>) {
  return JSON.parse(await tools[name](input) as string);
}

it.each([
  ['navigate_to', { path: '/cases/search', confirmed: true }],
  ['sign_in_demo_role', { role: 'admin', confirmed: 'true' }],
] as const)('asks the human even when %s input claims confirmation', async (name, input) => {
  confirm.mockReturnValue(false);
  const result = await run(name, input);
  expect(confirm).toHaveBeenCalledOnce();
  expect(result).toMatchObject({ ok: false, code: 'needs_confirmation' });
  expect(navigateApp).not.toHaveBeenCalled();
});

it('navigates only after the human agrees', async () => {
  confirm.mockReturnValue(true);
  expect(await run('navigate_to', { path: '/cases/search' })).toMatchObject({ ok: true });
  expect(confirm).toHaveBeenCalledWith('Allow the agent to navigate to /cases/search?');
  expect(navigateApp).toHaveBeenCalledWith('/cases/search');
});

it.each(['', '//example.com', '/api/v1/cases', 'cases/search'])(
  'rejects %j without asking the human',
  async (path) => {
    const result = await run('navigate_to', { path });
    expect(result.ok).toBe(false);
    expect(confirm).not.toHaveBeenCalled();
    expect(navigateApp).not.toHaveBeenCalled();
  },
);
