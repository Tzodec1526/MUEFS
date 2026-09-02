import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  applyDemoRole,
  applySessionFromProfile,
  getDemoCourtId,
  getDemoCourtName,
  getDemoRole,
  hasSession,
} from './LoginScreen';

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
    vi.stubGlobal('window', { dispatchEvent: vi.fn() });
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

  it('hasSession is true when a JWT is stored even without demo_role', () => {
    expect(hasSession()).toBe(false);
    localStorage.setItem('auth_token', 'jwt');
    expect(hasSession()).toBe(true);
    expect(getDemoRole()).toBeNull();
  });

  it('applySessionFromProfile maps clerk user_type and court assignment', () => {
    applySessionFromProfile({
      user_type: 'clerk',
      court_assignments: [
        { court_id: 9, role: 'clerk', court_name: 'Washtenaw Circuit' },
      ],
    });
    expect(getDemoRole()).toBe('clerk');
    expect(getDemoCourtId()).toBe(9);
    expect(getDemoCourtName()).toBe('Washtenaw Circuit');
  });

  it('applySessionFromProfile maps self_represented to srl', () => {
    applySessionFromProfile({ user_type: 'self_represented' });
    expect(getDemoRole()).toBe('srl');
  });

  it('applyDemoRole still sets the demo clerk court when no assignment is given', () => {
    applyDemoRole('clerk');
    expect(getDemoCourtId()).toBe(3);
  });
});
