import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { toolsForRole } from './catalog';
import { TOOL_DEFINITIONS } from './definitions';
import { examplePrompts, suggestNextStep } from './guidance';

const ROLES = [null, 'public', 'attorney', 'srl', 'clerk', 'admin'];
const PARAMETERS = new Set(TOOL_DEFINITIONS.flatMap(
  t => Object.keys((t.inputSchema as { properties?: Record<string, unknown> }).properties ?? {}),
));

describe.each([true, false])('demo build %s', demo => {
  beforeEach(() => { vi.stubEnv('VITE_ALLOW_DEMO_MODE', String(demo)); });
  afterEach(() => { vi.unstubAllEnvs(); });

  it.each(ROLES)('suggests only a tool registered for %s', role => {
    const { tool, hint } = suggestNextStep(role);
    expect(hint).not.toBe('');
    if (tool !== null) expect(toolsForRole(role).map(t => t.name)).toContain(tool);
  });

  it('asks an anonymous visitor to sign in the way this build allows', () => {
    const next = suggestNextStep(null);
    if (demo) expect(next.tool).toBe('sign_in_demo_role');
    else expect(next).toEqual({ tool: null, hint: expect.stringContaining('sign in at /login') });
  });

  it('writes example prompts that name only tools registered for their role', () => {
    for (const { role, prompt } of examplePrompts()) {
      const registered = toolsForRole(role).map(t => t.name as string);
      for (const word of prompt.match(/\b[a-z]+(?:_[a-z0-9]+)+\b/g) ?? []) {
        if (!PARAMETERS.has(word)) expect(registered, `${word} in: ${prompt}`).toContain(word);
      }
    }
  });
});
