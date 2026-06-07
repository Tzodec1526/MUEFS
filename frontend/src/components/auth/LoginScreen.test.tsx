import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getDemoRole, getDemoCourtId, getDemoCourtName } from './LoginScreen';

describe('demo auth helpers (localStorage backed)', () => {
  beforeEach(() => {
    // Provide a minimal localStorage mock so tests run in node env without jsdom
    const store: Record<string, string> = {};
    const mock = {
      getItem: (k: string) => (k in store ? store[k] : null),
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
      clear: () => { Object.keys(store).forEach(k => delete store[k]); },
    };
    vi.stubGlobal('localStorage', mock);
    localStorage.clear();
  });

  it('getDemoRole returns null by default', () => {
    expect(getDemoRole()).toBeNull();
  });

  it('getDemoRole returns value after set', () => {
    localStorage.setItem('demo_role', 'attorney');
    expect(getDemoRole()).toBe('attorney');
  });

  it('getDemoCourtId parses number or null', () => {
    expect(getDemoCourtId()).toBeNull();
    localStorage.setItem('demo_court_id', '3');
    expect(getDemoCourtId()).toBe(3);
  });

  it('getDemoCourtName roundtrip', () => {
    localStorage.setItem('demo_court_name', '3rd Circuit');
    expect(getDemoCourtName()).toBe('3rd Circuit');
  });
});
