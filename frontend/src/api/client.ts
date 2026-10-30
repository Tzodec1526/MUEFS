import axios, { AxiosError, CanceledError, isCancel, type InternalAxiosRequestConfig } from 'axios';
import { isDemoBuild } from '../config/demoMode';
import { errorMessage } from '../utils/errors';
import {
  clearSession, isCurrentSession, oidcSessionExpected, sessionSnapshot, SessionChangedError, tokenForRequest,
  type SessionSnapshot,
} from '../auth/keycloak';
import { isPublicPath } from '../auth/publicPath';
import { demoUserId } from '../auth/session';

// Same-origin by default: the hosted demo serves the API and UI together, and the
// Vite dev proxy forwards /api to the backend. Set VITE_API_URL only for a split
// deployment (separate frontend host + backend host).
const API_BASE_URL = import.meta.env.VITE_API_URL || '';
type SessionConfig = InternalAxiosRequestConfig & { muefsSession?: SessionSnapshot };

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

export function actionErrorMessage(error: unknown, fallback: string): string | null {
  return isCancel(error) ? null : errorMessage(error, fallback);
}

function expireSession(expected: SessionSnapshot): void {
  if (!clearSession(expected)) return;
  const { pathname, search, hash } = window.location;
  if (!isPublicPath(pathname) && pathname !== '/login' && !pathname.startsWith('/auth/')) {
    window.location.href = `/login?reason=expired&next=${encodeURIComponent(pathname + search + hash)}`;
  }
}

apiClient.interceptors.request.use(async (config: SessionConfig) => {
  const expected = sessionSnapshot();
  let token: string | null;
  try {
    token = await tokenForRequest();
  } catch (error) {
    if (error instanceof SessionChangedError || !isCurrentSession(expected)) {
      throw new CanceledError('The signed-in account changed.', config);
    }
    if (expected.token) expireSession(expected);
    throw new AxiosError('Your court sign-in could not be renewed. Please sign in again.', 'AUTH_EXPIRED', config);
  }
  if (!isCurrentSession(expected)) throw new CanceledError('The signed-in account changed.', config);
  config.muefsSession = { ...expected, token };
  if (token) config.headers.Authorization = `Bearer ${token}`;

  if (isDemoBuild() && !oidcSessionExpected() && !token) {
    const userId = demoUserId();
    if (userId) config.headers['X-Demo-User-Id'] = String(userId);
    const secret = import.meta.env.VITE_DEMO_MODE_SECRET
      || (window as Window & { __MUEFS_DEMO_SECRET__?: string }).__MUEFS_DEMO_SECRET__;
    if (secret) config.headers['X-Demo-Auth-Secret'] = secret;
  }
  return config;
});

apiClient.interceptors.response.use(
  response => {
    const expected = (response.config as SessionConfig).muefsSession;
    if (expected && !isCurrentSession(expected)) throw new CanceledError('The signed-in account changed.', response.config);
    return response;
  },
  (error) => {
    const expected = (error.config as SessionConfig | undefined)?.muefsSession;
    if (expected && !isCurrentSession(expected)) {
      return Promise.reject(new CanceledError('The signed-in account changed.', error.config));
    }
    if (error.response?.status === 401 && expected?.token) expireSession(expected);
    return Promise.reject(error);
  }
);
