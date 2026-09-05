import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { handleKeycloakCallback, safeLoginReturnPath, startKeycloakLogin } from './keycloakPkce';

beforeEach(() => {
  for (const storage of ['sessionStorage', 'localStorage']) {
    const values = new Map<string, string>();
    vi.stubGlobal(storage, {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
      removeItem: (key: string) => { values.delete(key); },
    });
  }
  vi.stubGlobal('window', {
    location: { origin: 'https://filing.example.gov', href: '' },
    dispatchEvent: vi.fn(),
  });
  vi.stubEnv('VITE_KEYCLOAK_URL', 'https://identity.example.gov');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ access_token: 'test-token' })),
  ));
});

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it('returns to the filing link after a state-checked code exchange and consumes the login attempt', async () => {
  const destination = '/filings/42/history?view=receipt#transactions';
  await startKeycloakLogin(destination);
  const authorization = new URL(window.location.href);
  const callback = new URLSearchParams({
    code: 'authorization-code', state: authorization.searchParams.get('state')!,
  });
  expect(await handleKeycloakCallback(callback.toString())).toBe(destination);
  expect(localStorage.getItem('auth_token')).toBe('test-token');
  expect(await handleKeycloakCallback(callback.toString())).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('rejects a callback with the wrong state before exchanging its code', async () => {
  await startKeycloakLogin('/notifications');
  expect(await handleKeycloakCallback('code=authorization-code&state=wrong')).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
  expect(localStorage.getItem('auth_token')).toBeNull();
});

it('rejects external destinations and sign-in loops', () => {
  for (const destination of [
    null, 'https://elsewhere.example', '//elsewhere.example', '/\\elsewhere.example',
    '/\t/elsewhere.example', '//[', '/login', '/login/', '/LOGIN', '/%6cogin', '/auth/callback',
  ]) {
    expect(safeLoginReturnPath(destination)).toBe('/');
  }
  expect(safeLoginReturnPath('/notifications')).toBe('/notifications');
});
