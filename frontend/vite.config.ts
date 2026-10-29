import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The Compose stack runs the API in another container.
const apiTarget = process.env.API_PROXY_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on this computer only; the container image opts in to other interfaces.
    port: 3000,
    // WebMCP requires an origin-isolated document (Chrome flag: enable-webmcp-testing).
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'credentialless',
    },
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/config.js': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
