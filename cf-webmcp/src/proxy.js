/**
 * Stable workers.dev front door → ephemeral Cloudflare quick tunnel.
 * Update ORIGIN when the quick-tunnel hostname rotates.
 * Deploy: npx wrangler deploy (workers:write only — no Containers scope needed)
 */
const ORIGIN = 'https://specifies-dna-bird-obligation.trycloudflare.com';

export default {
  async fetch(request) {
    const incoming = new URL(request.url);
    const target = new URL(incoming.pathname + incoming.search, ORIGIN);
    const headers = new Headers(request.headers);
    headers.set('Host', new URL(ORIGIN).host);
    return fetch(target, {
      method: request.method,
      headers,
      body: request.body,
      redirect: 'manual',
    });
  },
};
