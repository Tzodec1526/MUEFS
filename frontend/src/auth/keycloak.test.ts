import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';

const sdk = vi.hoisted(() => ({ clients: [] as FakeClient[], init: undefined as Promise<boolean> | undefined }));
class FakeClient {
  token: string | undefined = 'access-a';
  authenticated = true;
  tokenParsed = { iss: 'https://identity.example.gov/realms/courts', sub: 'account-a', iat: 100, exp: 190 };
  init = vi.fn(() => sdk.init ?? Promise.resolve(true));
  login = vi.fn(async () => {});
  updateToken = vi.fn(async () => false);
  clearToken = vi.fn(() => { this.token = undefined; this.authenticated = false; });
  createLogoutUrl = vi.fn(() => 'https://identity.example.gov/logout');
}
vi.mock('keycloak-js', () => ({ default: class extends FakeClient {
  constructor() { super(); sdk.clients.push(this); }
} }));

let auth: typeof import('./keycloak');
let api: typeof import('../api/client');
beforeEach(async () => {
  vi.resetModules();
  sdk.clients.length = 0;
  sdk.init = undefined;
  for (const storage of ['sessionStorage', 'localStorage']) {
    const values = new Map<string, string>();
    vi.stubGlobal(storage, {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
      removeItem: (key: string) => { values.delete(key); },
    });
  }
  vi.stubGlobal('window', {
    location: { origin: 'https://filing.example.gov', pathname: '/filings/new', search: '?case=42', hash: '#documents', href: '' },
    dispatchEvent: vi.fn(),
  });
  vi.stubEnv('VITE_KEYCLOAK_URL', 'https://identity.example.gov');
  vi.stubEnv('VITE_ALLOW_DEMO_MODE', 'false');
  auth = await import('./keycloak');
  api = await import('../api/client');
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

async function signIn(subject = 'account-a') {
  await auth.startKeycloakLogin('/filings/42/history?view=receipt#transactions');
  const client = sdk.clients[sdk.clients.length - 1];
  client.tokenParsed.sub = subject;
  client.token = `access-${subject}`;
  await auth.handleKeycloakCallback();
  return client;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function pendingRequest() {
  const response = deferred<AxiosResponse>();
  const sent = deferred<InternalAxiosRequestConfig>();
  const adapter = vi.fn((config: InternalAxiosRequestConfig) => { sent.resolve(config); return response.promise; });
  return { response, sent: sent.promise, adapter };
}

it('shares callback completion, keeps credentials in memory and preserves the private destination', async () => {
  await auth.startKeycloakLogin('/filings/42/history?view=receipt#transactions');
  const first = auth.handleKeycloakCallback();
  expect(auth.handleKeycloakCallback()).toBe(first);
  expect(await first).toBe('/filings/42/history?view=receipt#transactions');
  expect(auth.accessToken()).toBe('access-a');
  expect(localStorage.getItem('auth_token')).toBeNull();
  expect(localStorage.getItem(auth.SESSION_KEY)).not.toContain('access-a');
  expect(sdk.clients[0].init).toHaveBeenCalledTimes(1);
});

it('replaces a legacy stored credential with a nonsecret SSO restoration hint', () => {
  localStorage.setItem('auth_token', 'old-credential');
  auth.migrateStoredToken();
  expect(localStorage.getItem('auth_token')).toBeNull();
  expect(auth.oidcSessionExpected()).toBe(true);
  expect(auth.accessToken()).toBeNull();
});

it('preserves the account marker when another tab restores the same account', async () => {
  await signIn();
  const key = auth.sessionKey();
  await signIn();
  expect(auth.sessionKey()).toBe(key);
});

it('does not accept an OAuth completion after sign-out', async () => {
  await auth.startKeycloakLogin();
  auth.clearSession();
  await expect(auth.handleKeycloakCallback()).rejects.toBeInstanceOf(auth.SessionChangedError);
  expect(auth.accessToken()).toBeNull();
  expect(auth.oidcSessionExpected()).toBe(false);
});

it('discards a timed-out OAuth initializer even when it eventually succeeds', async () => {
  await auth.startKeycloakLogin();
  // The callback is a fresh document; reset only module memory, retaining its login attempt.
  vi.resetModules();
  auth = await import('./keycloak');
  const pending = deferred<boolean>();
  sdk.init = pending.promise;
  vi.useFakeTimers();
  const callback = auth.handleKeycloakCallback();
  const failure = expect(callback).rejects.toThrow('did not respond in time');
  await vi.advanceTimersByTimeAsync(15_001);
  await failure;
  pending.resolve(true);
  await vi.advanceTimersByTimeAsync(1);
  expect(auth.accessToken()).toBeNull();
  expect(auth.oidcSessionExpected()).toBe(false);
  expect(sdk.clients[sdk.clients.length - 1].clearToken).toHaveBeenCalled();
  await expect(auth.handleKeycloakCallback()).rejects.toThrow('did not respond in time');
});

it('ignores a late 401 from an older token and never repeats the submitted POST', async () => {
  const client = await signIn();
  const pending = pendingRequest();
  const request = api.apiClient.post('/filings/42/submit', {}, { adapter: pending.adapter });
  const failure = expect(request).rejects.toMatchObject({ response: { status: 401 } });
  const config = await pending.sent;
  client.token = 'renewed-access';
  pending.response.reject(new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined,
    { status: 401, statusText: '', headers: {}, config, data: {} }));
  await failure;
  expect(auth.accessToken()).toBe('renewed-access');
  expect(window.location.href).toBe('');
  expect(pending.adapter).toHaveBeenCalledTimes(1);
});

it.each([200, 401])('discards an old account response (%s) without clearing the new account', async status => {
  await signIn();
  const pending = pendingRequest();
  const request = api.apiClient.get('/filings', { adapter: pending.adapter });
  const failure = expect(request).rejects.toMatchObject({ code: 'ERR_CANCELED' });
  const config = await pending.sent;
  await signIn('account-b');
  const response = { status, statusText: '', headers: {}, config, data: { private: 'account-a' } };
  if (status === 200) pending.response.resolve(response);
  else pending.response.reject(new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, response));
  await failure;
  expect(auth.accessToken()).toBe('access-account-b');
  expect(window.location.href).toBe('');
});

it('discards an old request while a new sign-in is still pending', async () => {
  await signIn();
  const pending = pendingRequest();
  const request = api.apiClient.get('/filings', { adapter: pending.adapter });
  const failure = expect(request).rejects.toMatchObject({ code: 'ERR_CANCELED' });
  const config = await pending.sent;
  await auth.startKeycloakLogin();
  pending.response.reject(new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined,
    { status: 401, statusText: '', headers: {}, config, data: {} }));
  await failure;
  await auth.handleKeycloakCallback();
  expect(auth.accessToken()).toBe('access-a');
  expect(window.location.href).toBe('');
});

it.each([
  ['signs out', { generation: 'other-tab', restore: false }],
  ['signs in a different account', {
    generation: 'other-tab', restore: true, issuer: 'https://identity.example.gov/realms/courts', subject: 'account-b',
  }],
])('continues anonymously after another tab %s', async (_, otherTabMarker) => {
  const client = await signIn();
  const activity = await import('../webmcp/activity');
  activity.logAgentActivity('search_cases', { party_name: 'Smith' }, true, 12);
  const inFlight = pendingRequest();
  const stale = api.apiClient.get('/filings', { adapter: inFlight.adapter });
  const discarded = expect(stale).rejects.toMatchObject({ code: 'ERR_CANCELED' });
  const config = await inFlight.sent;

  // The other tab rewrites the shared marker; this tab only learns of it from storage.
  localStorage.setItem(auth.SESSION_KEY, JSON.stringify(otherTabMarker));
  inFlight.response.resolve({ status: 200, statusText: '', headers: {}, config, data: { private: 'account-a' } });
  await discarded;

  const adapter = vi.fn(async (sent: InternalAxiosRequestConfig) => (
    { status: 200, statusText: '', headers: {}, config: sent, data: { cases: [] } }));
  await api.apiClient.get('/cases/search', { adapter });
  await api.apiClient.get('/cases/search', { adapter });
  expect(adapter).toHaveBeenCalledTimes(2);
  expect(adapter.mock.calls.some(([sent]) => sent.headers.has('Authorization'))).toBe(false);
  expect(auth.accessToken()).toBeNull();
  expect(client.clearToken).toHaveBeenCalled();
  expect(activity.getAgentActivity()).toEqual([]);
});

it("clears the agent activity log when a different account signs in, not when the same one returns", async () => {
  const activity = await import('../webmcp/activity');
  await signIn();
  activity.logAgentActivity('search_cases', { party_name: 'Smith' }, true, 12);
  await signIn();
  expect(activity.getAgentActivity()).toHaveLength(1);
  await signIn('account-b');
  expect(activity.getAgentActivity()).toEqual([]);
});

it('stops a mutation when renewal fails and preserves its unsaved filing draft', async () => {
  const client = await signIn();
  sessionStorage.setItem('muefs_filing_draft:v2:1:new', 'unsaved');
  client.updateToken.mockImplementation(async () => { client.clearToken(); throw new Error('invalid_grant'); });
  const adapter = vi.fn();
  await expect(api.apiClient.post('/filings/42/submit', {}, { adapter })).rejects.toMatchObject({ code: 'AUTH_EXPIRED' });
  expect(adapter).not.toHaveBeenCalled();
  expect(auth.accessToken()).toBeNull();
  expect(auth.oidcSessionExpected()).toBe(false);
  expect(sessionStorage.getItem('muefs_filing_draft:v2:1:new')).toBe('unsaved');
  expect(window.location.href).toBe('/login?reason=expired&next=%2Ffilings%2Fnew%3Fcase%3D42%23documents');
});

it('does not restore a signed-out session when an in-flight renewal finishes', async () => {
  const client = await signIn();
  const renewal = deferred<boolean>();
  client.updateToken.mockReturnValue(renewal.promise);
  const adapter = vi.fn();
  const request = api.apiClient.post('/filings/42/submit', {}, { adapter });
  const failure = expect(request).rejects.toMatchObject({ code: 'ERR_CANCELED' });
  await vi.waitFor(() => expect(client.updateToken).toHaveBeenCalled());
  expect(auth.signOut()).toBe('https://identity.example.gov/logout');
  client.token = 'late-access-token';
  renewal.resolve(true);
  await failure;
  expect(auth.accessToken()).toBeNull();
  expect(adapter).not.toHaveBeenCalled();
});

it('bounds a hung renewal and discards its eventual token', async () => {
  const client = await signIn();
  vi.useFakeTimers();
  const renewal = deferred<boolean>();
  client.updateToken.mockReturnValue(renewal.promise);
  const adapter = vi.fn();
  const request = api.apiClient.post('/filings/42/submit', {}, { adapter });
  const failure = expect(request).rejects.toMatchObject({ code: 'AUTH_EXPIRED' });
  await vi.advanceTimersByTimeAsync(15_001);
  await failure;
  client.token = 'late-access-token';
  renewal.resolve(true);
  await vi.advanceTimersByTimeAsync(1);
  expect(auth.accessToken()).toBeNull();
  expect(adapter).not.toHaveBeenCalled();
});

it('does not fall back to demo credentials while an OIDC account needs restoration', async () => {
  vi.stubEnv('VITE_ALLOW_DEMO_MODE', 'true');
  vi.stubEnv('VITE_DEMO_MODE_SECRET', 'demo-secret');
  localStorage.setItem('demo_role', 'admin');
  localStorage.setItem(auth.SESSION_KEY, JSON.stringify({ restore: true }));
  const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => ({ status: 200, statusText: '', headers: {}, config, data: {} }));
  await api.apiClient.get('/cases/search', { adapter });
  expect(adapter.mock.calls[0][0].headers.has('X-Demo-User-Id')).toBe(false);
  expect(adapter.mock.calls[0][0].headers.has('X-Demo-Auth-Secret')).toBe(false);
});

it('rejects external destinations and sign-in loops', () => {
  for (const destination of [
    null, 'https://elsewhere.example', '//elsewhere.example', '/\\elsewhere.example',
    '/\t/elsewhere.example', '//[', '/login', '/login/', '/LOGIN', '/%6cogin', '/auth/callback',
  ]) expect(auth.safeLoginReturnPath(destination)).toBe('/');
  expect(auth.safeLoginReturnPath('/notifications')).toBe('/notifications');
});
