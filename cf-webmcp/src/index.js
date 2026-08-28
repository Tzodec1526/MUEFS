/**
 * Cloudflare Containers edge for MUEFS WebMCP demo.
 * Proxies all traffic to a single always-on-ish container instance.
 */
import { Container } from '@cloudflare/containers';

export class MuefsDemoContainer extends Container {
  defaultPort = 8000;
  // Keep warm through judge sessions; platform may still migrate hosts.
  sleepAfter = '30m';
  envVars = {
    ALLOW_DEMO_MODE: 'true',
    DEMO_ISOLATED_SESSIONS: 'true',
    DEMO_MODE_SECRET: 'webmcp-challenge',
    DEBUG: 'false',
    ENABLE_API_DOCS: 'false',
    PAYMENTS_ARE_SIMULATED: 'true',
    RATE_LIMIT_ENABLED: 'true',
    RATE_LIMIT_BACKEND: 'memory',
  };
}

export default {
  async fetch(request, env) {
    // Single sticky instance for the public challenge demo.
    const stub = env.MUEFS_DEMO.getByName('webmcp-challenge');
    return stub.fetch(request);
  },
};
