/** Pull the FastAPI/axios error detail string out of an unknown error, if present. */
export function getErrorDetail(err: unknown): string | undefined {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap(item => item && typeof item.msg === 'string' ? [item.msg] : []);
    return messages.join(' ') || undefined;
  }
  return undefined;
}
