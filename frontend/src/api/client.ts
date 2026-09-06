import axios from 'axios';
import { isDemoBuild } from '../config/demoMode';
import { emitToast } from '../utils/toastBus';

// Same-origin by default: the hosted demo serves the API and UI together, and the
// Vite dev proxy forwards /api to the backend. Set VITE_API_URL only for a split
// deployment (separate frontend host + backend host).
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

function demoModeSecret(): string | undefined {
  const fromBuild = import.meta.env.VITE_DEMO_MODE_SECRET;
  if (fromBuild) return fromBuild;
  const runtime = (window as Window & { __MUEFS_DEMO_SECRET__?: string }).__MUEFS_DEMO_SECRET__;
  return runtime || undefined;
}

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// This client uses bearer tokens in browser storage. IdP session cookies do not
// replace the API token; a server-owned session would need a separate backend flow.
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  if (isDemoBuild()) {
    const demoRole = localStorage.getItem('demo_role');
    const roleToUserId: Record<string, number> = {
      attorney: 1,
      clerk: 2,
      admin: 3,
      self_represented: 4,
      srl: 4,
      public: 5,
    };
    if (demoRole && roleToUserId[demoRole]) {
      config.headers['X-Demo-User-Id'] = String(roleToUserId[demoRole]);
    }
    const demoSecret = demoModeSecret();
    if (demoSecret) {
      config.headers['X-Demo-Auth-Secret'] = demoSecret;
    }
  }

  return config;
});

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
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
    if (status === 401) {
      const hadJwt = Boolean(localStorage.getItem('auth_token'));
      localStorage.removeItem('auth_token');
      // Only bounce real JWT sessions. Demo-role sandboxes often get a transient
      // 401 (secret misconfig, race); hard-redirecting to /login makes the demo
      // unusable within seconds of signing in.
      if (!hadJwt) {
        return Promise.reject(error);
      }
      const path = window.location.pathname;
      const onPublicPath = /^\/cases\/(search|\d+)\/?$/.test(path);
      const role = localStorage.getItem('demo_role');
      if (role && role !== 'public' && !onPublicPath && path !== '/login') {
        window.location.href = `/login?next=${encodeURIComponent(path + window.location.search + window.location.hash)}`;
      }
    }
    return Promise.reject(error);
  }
);
