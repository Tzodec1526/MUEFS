import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// The Compose stack runs the API in another container.
const apiTarget = process.env.API_PROXY_TARGET || 'http://localhost:8000';

const nodeTests = ['src/styles/global.css.test.ts'];

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [{ name: 'vendor', test: /node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/ }],
        },
      },
    },
  },
  test: {
    projects: [
      {
        extends: true,
        test: { name: 'jsdom', environment: 'jsdom', exclude: [...configDefaults.exclude, ...nodeTests] },
      },
      {
        extends: true,
        test: { name: 'node', environment: 'node', include: nodeTests },
      },
    ],
  },
  server: {
    // Listen on this computer only; the container image opts in to other interfaces.
    port: 3000,
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
