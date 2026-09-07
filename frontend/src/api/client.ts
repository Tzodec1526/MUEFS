import axios, { AxiosError, CanceledError, type InternalAxiosRequestConfig } from 'axios';
import { isDemoBuild } from '../config/demoMode';
import { emitToast } from '../utils/toastBus';
import {
  clearSession, isCurrentSession, oidcSessionExpected, sessionSnapshot, SessionChangedError, tokenForRequest,
  type SessionSnapshot,
} from '../auth/keycloak';

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

function expireSession(expected: SessionSnapshot): void {
  if (!clearSession(expected)) return;
  const { pathname, search, hash } = window.location;
  const publicPath = /^\/cases\/(search|\d+)\/?$/.test(pathname)
    || pathname.startsWith('/courts/') || pathname.startsWith('/agent');
  if (!publicPath && pathname !== '/login' && !pathname.startsWith('/auth/')) {
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
    const roleToUserId: Record<string, number> = { attorney: 1, clerk: 2, admin: 3, self_represented: 4, srl: 4, public: 5 };
    const role = localStorage.getItem('demo_role');
    if (role && roleToUserId[role]) config.headers['X-Demo-User-Id'] = String(roleToUserId[role]);
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
    const status = error.response?.status;
    const detail = error.response?.data?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : status === 429
          ? 'Too many requests. Please wait a moment and try again.'
          : status === 403
            ? 'You do not have permission to do that.'
            : null;
    if (message && status !== 401) {
      emitToast(message, 'error');
    }
    if (status === 401 && expected?.token) expireSession(expected);
    return Promise.reject(error);
  }
);
