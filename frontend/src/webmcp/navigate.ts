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
  '/admin',
  '/courts',
  '/notifications',
  '/service',
];

// eslint-disable-next-line no-control-regex -- Browsers strip these anywhere in a URL.
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;
// eslint-disable-next-line no-control-regex -- Browsers also normalize these in a path.
const UNSAFE_PATH_CHARACTERS = /[\\\u0000-\u0020\u007f]/;

export function isSafeAppPath(path: string): boolean {
  if (!path.startsWith('/')) return false;
  if (path.startsWith('//') || CONTROL_CHARACTERS.test(path)) return false;
  // A query or fragment may contain spaces; the path itself may not.
  const rawPathname = path.split(/[?#]/, 1)[0];
  if (UNSAFE_PATH_CHARACTERS.test(rawPathname)) return false;
  let pathname: string;
  try {
    pathname = decodeURIComponent(rawPathname);
  } catch { return false; }
  if (UNSAFE_PATH_CHARACTERS.test(pathname)
    || pathname.split('/').some(part => part === '..' || part === '.')) return false;
  return ALLOWED_PREFIXES.some(
    (prefix) => pathname === prefix || (prefix !== '/' && pathname.startsWith(`${prefix}/`)),
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
