/** Structured tool results — always JSON strings for agent parsers. */

export function toolJson(data: unknown): string {
  return JSON.stringify(data, null, 0);
}

export function toolError(message: string, code?: string): string {
  return toolJson({ ok: false, error: message, code: code || 'error' });
}

export function toolOk<T extends Record<string, unknown>>(payload: T): string {
  return toolJson({ ok: true, ...payload });
}

/** Strip control chars; cap length so docket text cannot be used for prompt injection. */
export function sanitizeAgentText(value: string, maxLen = 500): string {
  return value
    // eslint-disable-next-line no-control-regex -- strip control chars from untrusted court records
    .replace(/[\u0000-\u001f\u007f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, maxLen);
}
