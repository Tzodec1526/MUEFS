/** Structured tool results — always JSON strings for agent parsers. */

export function toolError(message: string, code?: string): string {
  return JSON.stringify({ ok: false, error: message, code: code || 'error' });
}

export function toolOk<T extends Record<string, unknown>>(payload: T): string {
  return JSON.stringify({ ok: true, ...payload });
}

/** Normalize and truncate docket excerpts. Their content remains untrusted. */
export function sanitizeAgentText(value: string, maxLen = 500): string {
  return value
    // eslint-disable-next-line no-control-regex -- strip control chars from untrusted court records
    .replace(/[\u0000-\u001f\u007f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, maxLen);
}
