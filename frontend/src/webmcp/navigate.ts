/** Same-origin navigation for agent-driven workflows. */

export const MUEFS_NAVIGATE_EVENT = 'muefs-navigate';

const ALLOWED_PREFIXES = [
  '/',
  '/login',
  '/cases',
  '/filing',
  '/filings',
  '/favorites',
  '/clerk',
  '/agent',
];

export function isSafeAppPath(path: string): boolean {
  if (!path.startsWith('/')) return false;
  if (path.includes('://') || path.startsWith('//')) return false;
  if (path.includes('..')) return false;
  return ALLOWED_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`) || path.startsWith(`${prefix}?`),
  );
}

let spaBridgeArmed = false;

export function setNavigateBridgeArmed(armed: boolean): void {
  spaBridgeArmed = armed;
}

export function navigateApp(path: string): { ok: true; path: string } | { ok: false; error: string } {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  if (!isSafeAppPath(normalized)) {
    return { ok: false, error: 'Path must stay within the MUEFS application.' };
  }

  if (spaBridgeArmed && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(MUEFS_NAVIGATE_EVENT, { detail: { path: normalized } }));
    return { ok: true, path: normalized };
  }

  window.location.assign(normalized);
  return { ok: true, path: normalized };
}
