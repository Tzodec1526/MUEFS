/**
 * Keycloak OIDC authorization-code flow with PKCE (production path).
 * Demo builds use role-picker headers instead; this hook is for real IdP deployments.
 */

import { notifyDemoRoleChanged } from '../components/auth/LoginScreen';

const STORAGE_VERIFIER = 'muefs_pkce_verifier';
const STORAGE_STATE = 'muefs_pkce_state';
const STORAGE_RETURN_PATH = 'muefs_login_return_path';

export function safeLoginReturnPath(value: string | null): string {
  if (!value?.startsWith('/')) return '/';
  try {
    const destination = new URL(value, window.location.origin);
    if (destination.origin !== window.location.origin
      || /^\/(?:login|auth)(?:\/|$)/i.test(decodeURIComponent(destination.pathname))) return '/';
    return destination.pathname + destination.search + destination.hash;
  } catch {
    return '/';
  }
}

function baseUrl(): string {
  const url = import.meta.env.VITE_KEYCLOAK_URL;
  if (!url) throw new Error('VITE_KEYCLOAK_URL is not configured');
  return url.replace(/\/$/, '');
}

function realm(): string {
  return import.meta.env.VITE_KEYCLOAK_REALM || 'muefs';
}

function clientId(): string {
  return import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'muefs-frontend';
}

function redirectUri(): string {
  const explicit = import.meta.env.VITE_KEYCLOAK_REDIRECT_URI;
  if (explicit) return explicit;
  return `${window.location.origin}/auth/callback`;
}

function randomString(bytes = 32): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return btoa(String.fromCharCode(...arr))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

async function sha256Base64Url(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

export function keycloakConfigured(): boolean {
  return Boolean(import.meta.env.VITE_KEYCLOAK_URL);
}

export async function startKeycloakLogin(returnPath = '/'): Promise<void> {
  const verifier = randomString(48);
  const challenge = await sha256Base64Url(verifier);
  const state = randomString(16);
  sessionStorage.setItem(STORAGE_VERIFIER, verifier);
  sessionStorage.setItem(STORAGE_STATE, state);
  sessionStorage.setItem(STORAGE_RETURN_PATH, safeLoginReturnPath(returnPath));

  const params = new URLSearchParams({
    client_id: clientId(),
    response_type: 'code',
    scope: 'openid profile email',
    redirect_uri: redirectUri(),
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  });

  window.location.href =
    `${baseUrl()}/realms/${realm()}/protocol/openid-connect/auth?${params}`;
}

export async function handleKeycloakCallback(
  search: string,
): Promise<string | null> {
  const params = new URLSearchParams(search);
  const code = params.get('code');
  const state = params.get('state');
  const savedState = sessionStorage.getItem(STORAGE_STATE);
  const verifier = sessionStorage.getItem(STORAGE_VERIFIER);
  const returnPath = safeLoginReturnPath(sessionStorage.getItem(STORAGE_RETURN_PATH));

  sessionStorage.removeItem(STORAGE_STATE);
  sessionStorage.removeItem(STORAGE_VERIFIER);
  sessionStorage.removeItem(STORAGE_RETURN_PATH);

  if (!code || !verifier || !state || state !== savedState) {
    return null;
  }

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: clientId(),
    code,
    redirect_uri: redirectUri(),
    code_verifier: verifier,
  });

  const tokenUrl = `${baseUrl()}/realms/${realm()}/protocol/openid-connect/token`;
  const response = await fetch(tokenUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  if (!response.ok) return null;

  const tokens = (await response.json()) as { access_token?: string };
  if (!tokens.access_token) return null;

  localStorage.setItem('auth_token', tokens.access_token);
  localStorage.removeItem('demo_role');
  notifyDemoRoleChanged();
  return returnPath;
}
