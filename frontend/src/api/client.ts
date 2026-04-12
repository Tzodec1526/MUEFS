import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
