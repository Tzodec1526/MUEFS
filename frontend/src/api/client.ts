import axios from 'axios';

// Same-origin by default: the hosted demo serves the API and UI together, and the
// Vite dev proxy forwards /api to the backend. Set VITE_API_URL only for a split
// deployment (separate frontend host + backend host).
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for auth token
// SECURITY NOTE: In production, use httpOnly cookies set by Keycloak
// instead of localStorage to prevent XSS-based token theft.
// This localStorage approach is for MVP/demo only.
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // Demo only: production builds require explicit VITE_ALLOW_DEMO_MODE=true|1.
  // Dev server defaults to on unless VITE_ALLOW_DEMO_MODE is false|0 (local UX).
  const rawDemo = import.meta.env.VITE_ALLOW_DEMO_MODE;
  const demoHeadersOn =
    rawDemo === 'true' ||
    rawDemo === '1' ||
    (import.meta.env.DEV && rawDemo !== 'false' && rawDemo !== '0');
  if (demoHeadersOn) {
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
  }

  return config;
});

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      // Only send a genuinely authenticated session back to login. Never bounce an
      // anonymous/public visitor browsing the public records path -- that would
      // contradict the "no account needed" public-records access.
      const path = window.location.pathname;
      const onPublicPath = path.startsWith('/cases');
      const role = localStorage.getItem('demo_role');
      if (role && role !== 'public' && !onPublicPath && path !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);
