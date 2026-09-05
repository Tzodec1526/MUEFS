import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  applyDemoRole,
  applySessionFromProfile,
  getDemoCourtId,
  getDemoCourtName,
  getDemoRole,
  hasSession,
} from './LoginScreen';

describe('identity session boundaries', () => {
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

  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

  it('requires a token outside demo mode even when role metadata remains', () => {
    vi.stubEnv('VITE_ALLOW_DEMO_MODE', 'false');
    applySessionFromProfile({ user_type: 'admin' });
    expect(hasSession()).toBe(false);
    localStorage.setItem('auth_token', 'jwt');
    expect(hasSession()).toBe(true);
    localStorage.removeItem('auth_token');
    expect(hasSession()).toBe(false);
    vi.stubEnv('VITE_ALLOW_DEMO_MODE', 'true');
    expect(hasSession()).toBe(true);
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

  it('does not invent a court for real staff and removes a previous assignment', () => {
    applyDemoRole('clerk');
    expect(getDemoCourtId()).toBe(3);
    applySessionFromProfile({ user_type: 'clerk', court_assignments: [] });
    expect(getDemoCourtId()).toBeNull();
    expect(getDemoCourtName()).toBeNull();
    expect(localStorage.getItem('administration_access')).toBe('false');
  });

  it('distinguishes a system administrator from a delegated court administrator', () => {
    applySessionFromProfile({ user_type: 'admin', court_assignments: [] });
    expect(getDemoRole()).toBe('admin');
    expect(getDemoCourtId()).toBeNull();
    applySessionFromProfile({ user_type: 'clerk', court_assignments: [{ court_id: 7, role: 'admin' }] });
    expect(getDemoRole()).toBe('clerk');
    expect(getDemoCourtId()).toBe(7);
    expect(localStorage.getItem('administration_access')).toBe('true');
  });

});
