import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearAgentActivity, getAgentActivity, logAgentActivity } from './activity';

describe('logAgentActivity', () => {
  beforeEach(() => {
    (globalThis as { window?: Window }).window = {
      dispatchEvent: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Window;
  });

  afterEach(() => {
    clearAgentActivity();
    delete (globalThis as { window?: Window }).window;
  });

  it('records tool name and ok status', () => {
    logAgentActivity('search_cases', { party_name: 'Smith' }, true, 42);
    const [entry] = getAgentActivity();
    expect(entry.tool).toBe('search_cases');
    expect(entry.ok).toBe(true);
    expect(entry.durationMs).toBe(42);
    expect(entry.summary).toContain('Smith');
  });

  it('dispatches custom event for UI feed', () => {
    logAgentActivity('get_agent_catalog', {}, true, 1);
    expect(window.dispatchEvent).toHaveBeenCalledOnce();
  });

  it('caps history at 40 entries', () => {
    for (let i = 0; i < 45; i++) {
      logAgentActivity('navigate_to', { path: `/p${i}` }, true, 1);
    }
    expect(getAgentActivity()).toHaveLength(40);
  });
});
