/** Structured tool results — always JSON strings for agent parsers. */

import { isAxiosError, isCancel } from 'axios';

/**
 * Why a tool call failed, so an agent can decide what to do next. docs/WEBMCP.md lists them.
 * - invalid: fix the input (or the request) and try again
 * - forbidden / not_found: the record is not available to this session
 * - needs_sign_in: the human must sign in, or switch to a role the tool needs
 * - unavailable: MUEFS could not answer (network, server, rate limit, account change); retry later
 * - needs_confirmation: the human declined in the browser
 * - needs_court_assignment: a clerk must choose a working court first
 * - cancelled: a newer submission of the same form replaced this one
 */
export type ToolErrorCode =
  | 'invalid' | 'forbidden' | 'not_found' | 'needs_sign_in' | 'unavailable'
  | 'needs_confirmation' | 'needs_court_assignment' | 'cancelled';

/** Extra fields for an error result; they cannot replace ok, error or code. */
type ErrorDetails = Record<string, unknown> & { ok?: never; error?: never; code?: never };

export function toolError(message: string, code: ToolErrorCode, details?: ErrorDetails): string {
  return JSON.stringify({ ok: false, error: message, code, ...details });
}

export function toolOk<T extends Record<string, unknown>>(payload: T): string {
  return JSON.stringify({ ok: true, ...payload });
}

/**
 * Normalize and truncate record text (captions, titles, descriptions). Its content remains
 * untrusted. Control and format characters, which include zero-width characters, bidi controls
 * and Unicode tag characters, become spaces; other default-ignorable code points (variation
 * selectors, reserved tag code points, fillers) are removed. None of them show in the UI, so
 * none may carry text to an agent.
 */
export function sanitizeAgentText(value: string, maxLen = 500): string {
  return value
    .replace(/[\p{Cc}\p{Cf}\u2028\u2029]/gu, ' ')
    .replace(/\p{Default_Ignorable_Code_Point}/gu, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, maxLen);
}

/** The server's explanation of a rejected request (FastAPI `detail`), if it gave one. */
function serverDetail(data: unknown): string | null {
  const detail = (data as { detail?: unknown } | null | undefined)?.detail;
  const text = typeof detail === 'string'
    ? detail
    : Array.isArray(detail)
      ? detail.map(item => (item as { msg?: unknown } | null)?.msg).filter(msg => typeof msg === 'string').join('; ')
      : '';
  const clean = sanitizeAgentText(text, 300);
  return clean || null;
}

/**
 * The tool result for a failed MUEFS API request, or null when the error is not an API
 * failure (a programming error, which should still surface as one).
 */
export function apiErrorResult(error: unknown): string | null {
  // The API client cancels requests made for an account that is no longer signed in.
  if (isCancel(error)) {
    return toolError(
      'The signed-in account changed during this call. Call get_agent_session, then try again.',
      'unavailable',
    );
  }
  if (!isAxiosError(error)) return null;
  const status = error.response?.status;
  if (status === undefined) {
    if (error.code === 'AUTH_EXPIRED') {
      return toolError('The court sign-in expired. Ask the human to sign in again at /login.', 'needs_sign_in');
    }
    return toolError('MUEFS could not be reached. Try again shortly.', 'unavailable');
  }
  const detail = serverDetail(error.response?.data);
  if (status === 401) {
    return toolError('This session is not signed in or its sign-in expired. Ask the human to sign in at /login.',
      'needs_sign_in', { status });
  }
  if (status === 403) return toolError(detail ?? 'This session may not see that record.', 'forbidden', { status });
  if (status === 404) return toolError(detail ?? 'That record does not exist.', 'not_found', { status });
  // Rate limits clear on their own, like server failures.
  if (status === 429 || status >= 500) {
    return toolError('MUEFS is unavailable right now. Try again shortly.', 'unavailable', { status });
  }
  return toolError(detail ?? `MUEFS rejected the request (HTTP ${status}).`, 'invalid', { status });
}
