import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { catalogForRole } from './catalog';
import { registerRoleTools } from './registerTools';

describe.each([true, false])('role catalog with demo mode %s', demo => {
  beforeEach(() => { vi.stubEnv('VITE_ALLOW_DEMO_MODE', String(demo)); });
  afterEach(() => { vi.unstubAllEnvs(); });
  it.each([null, 'public', 'attorney', 'srl', 'clerk', 'admin'])(
    'matches the tools actually registered for %s', async role => {
      const registerTool = vi.fn();
      await registerRoleTools({ registerTool }, role, new AbortController().signal);
      const names = registerTool.mock.calls.map(([tool]) => tool.name);
      expect(names.sort()).toEqual(catalogForRole(role).map(t => t.name).sort());
      expect(new Set(names).size).toBe(names.length);

      expect(names.includes('validate_filing')).toBe(role === 'attorney' || role === 'srl');
      expect(names.includes('get_clerk_review_queue')).toBe(role === 'clerk');
      expect(names.includes('sign_in_demo_role')).toBe(demo);
      expect(names.includes('get_current_demo_role')).toBe(demo);
    },
  );
});
