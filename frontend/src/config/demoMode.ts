/**
 * Matches api/client.ts: demo headers only when build allows (stakeholder / local demo).
 */
export function isDemoBuild(): boolean {
  const raw = import.meta.env.VITE_ALLOW_DEMO_MODE;
  if (raw === 'true' || raw === '1') return true;
  if (import.meta.env.DEV && raw !== 'false' && raw !== '0') return true;
  return false;
}
