import type Keycloak from 'keycloak-js';

export const SESSION_KEY = 'muefs_auth_session';
const LOGIN_KEY = 'muefs_login_attempt';
interface Marker { generation: string; restore: boolean; issuer?: string; subject?: string }
export interface SessionSnapshot { key: string; token: string | null; generation: number }
let generation = 0;
let initialized: Promise<Keycloak> | null = null;
let session: { client: Keycloak; key: string } | null = null;
let login: Promise<void> | null = null;
let callback: Promise<string | null> | null = null;

export class SessionChangedError extends Error {
  constructor() { super('The signed-in account changed. Open the current account before continuing.'); }
}

function marker(): Marker | null {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null'); } catch { return null; }
}

export function sessionKey(): string {
  return `${localStorage.getItem(SESSION_KEY) || ''}:${marker()?.restore ? '' : localStorage.getItem('demo_role') || ''}`;
}

export function accessToken(): string | null {
  return session?.key === sessionKey() ? session.client.token || null : null;
}

export function sessionSnapshot(): SessionSnapshot {
  return { key: sessionKey(), token: accessToken(), generation };
}

export function isCurrentSession(expected: SessionSnapshot): boolean {
  return expected.key === sessionKey() && expected.generation === generation;
}

export function keycloakConfigured(): boolean {
  return Boolean(import.meta.env.VITE_KEYCLOAK_URL);
}

export function oidcSessionExpected(): boolean {
  return marker()?.restore === true;
}

export function notifySessionChanged(): void {
  window.dispatchEvent(new Event('muefs-demo-role-changed'));
}

function forgetLocalSession(): void {
  generation++;
  session?.client.clearToken();
  session = null;
  initialized = null;
  login = null;
}

function clearProfile(): void {
  for (const key of ['auth_token', 'demo_role', 'demo_user_name', 'demo_court_id', 'administration_access']) {
    localStorage.removeItem(key);
  }
}

export function clearSession(expected?: SessionSnapshot): boolean {
  if (expected && (!isCurrentSession(expected)
    || (accessToken() && expected.token !== accessToken()))) return false;
  forgetLocalSession();
  clearProfile();
  localStorage.setItem(SESSION_KEY, JSON.stringify({ generation: crypto.randomUUID(), restore: false }));
  notifySessionChanged();
  return true;
}

export function migrateStoredToken(): void {
  // Older versions persisted access tokens. Keep only a sign-in hint on upgrade.
  if (!localStorage.getItem('auth_token')) return;
  localStorage.removeItem('auth_token');
  if (!localStorage.getItem(SESSION_KEY)) {
    localStorage.setItem(SESSION_KEY, JSON.stringify({ generation: crypto.randomUUID(), restore: true }));
  }
}

async function withDeadline<T>(operation: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([operation, new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error('The identity provider did not respond in time.')), 15_000);
    })]);
  } finally { clearTimeout(timer); }
}

function initialize(): Promise<Keycloak> {
  if (!initialized) {
    const started = generation;
    let canceled = false;
    initialized = withDeadline((async () => {
      const { default: Client } = await import('keycloak-js');
      if (!keycloakConfigured()) throw new Error('Court identity sign-in is not configured.');
      const client = new Client({
        url: import.meta.env.VITE_KEYCLOAK_URL,
        realm: import.meta.env.VITE_KEYCLOAK_REALM || 'muefs',
        clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'muefs-frontend',
      });
      await client.init({ pkceMethod: 'S256', responseMode: 'query', checkLoginIframe: false });
      if (canceled || started !== generation) { client.clearToken(); throw new SessionChangedError(); }
      return client;
    })()).catch(error => {
      // A timed-out initializer must never become a usable session later.
      canceled = true;
      if (started !== generation) throw new SessionChangedError();
      throw error;
    });
  }
  return initialized;
}

export function safeLoginReturnPath(value: string | null): string {
  if (!value?.startsWith('/')) return '/';
  try {
    const destination = new URL(value, window.location.origin);
    if (destination.origin !== window.location.origin
      || /^\/(?:login|auth)(?:\/|$)/i.test(decodeURIComponent(destination.pathname))) return '/';
    return destination.pathname + destination.search + destination.hash;
  } catch { return '/'; }
}

export function startKeycloakLogin(returnPath = '/'): Promise<void> {
  if (login) return login;
  forgetLocalSession();
  callback = null;
  const expected = sessionKey();
  sessionStorage.setItem(LOGIN_KEY, JSON.stringify({ key: expected, path: safeLoginReturnPath(returnPath) }));
  const operation = (async () => {
    const client = await initialize();
    if (expected !== sessionKey()) throw new SessionChangedError();
    await client.login({ redirectUri: import.meta.env.VITE_KEYCLOAK_REDIRECT_URI
      || `${window.location.origin}/auth/callback` });
  })().catch(error => { if (login === operation) login = null; throw error; });
  login = operation;
  return login;
}

export function handleKeycloakCallback(): Promise<string | null> {
  if (callback) return callback;
  const raw = sessionStorage.getItem(LOGIN_KEY);
  sessionStorage.removeItem(LOGIN_KEY);
  if (!raw) return Promise.resolve(null);
  const started = generation;
  let attempt: { key: string; path: string } | undefined;
  callback = (async () => {
    attempt = JSON.parse(raw) as { key: string; path: string };
    const client = await initialize();
    if (started !== generation) { client.clearToken(); throw new SessionChangedError(); }
    const issuer = client.tokenParsed?.iss, subject = client.tokenParsed?.sub;
    if (!client.authenticated || !client.token || typeof issuer !== 'string' || typeof subject !== 'string') {
      throw new Error('The identity provider did not complete sign-in. Please try again.');
    }
    const current = marker();
    const sameAccount = current?.restore && current.issuer === issuer && current.subject === subject;
    if (attempt.key !== sessionKey() && !sameAccount) { client.clearToken(); throw new SessionChangedError(); }
    if (!sameAccount) {
      clearProfile();
      localStorage.setItem(SESSION_KEY, JSON.stringify({ generation: crypto.randomUUID(), restore: true, issuer, subject }));
    }
    session = { client, key: sessionKey() };
    login = null;
    notifySessionChanged();
    return safeLoginReturnPath(attempt.path);
  })().catch(error => {
    if (!(error instanceof SessionChangedError) && typeof attempt?.key === 'string') {
      clearSession({ key: attempt.key, token: null, generation: started });
    }
    throw error;
  });
  return callback;
}

export async function tokenForRequest(): Promise<string | null> {
  const current = session;
  if (!current) return null;
  if (current.key !== sessionKey()) throw new SessionChangedError();
  const lifetime = (current.client.tokenParsed?.exp || 0) - (current.client.tokenParsed?.iat || 0);
  await withDeadline(current.client.updateToken(Math.min(30, Math.max(1, Math.floor(lifetime / 3)))));
  if (session !== current || current.key !== sessionKey()) throw new SessionChangedError();
  if (!current.client.token) throw new Error('Your court sign-in has expired.');
  return current.client.token;
}

export function signOut(): string | null {
  const url = accessToken() ? session!.client.createLogoutUrl({ redirectUri: `${window.location.origin}/login` }) : null;
  clearSession();
  return url;
}
