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

/** getErrorDetail for `responseType: 'blob'` requests, whose error bodies arrive as Blobs. */
export async function getBlobErrorDetail(err: unknown): Promise<string | undefined> {
  const body = (err as { response?: { data?: unknown } })?.response?.data;
  if (!(body instanceof Blob)) return getErrorDetail(err);
  try {
    return getErrorDetail({ response: { data: JSON.parse(await body.text()) } });
  } catch {
    return undefined;
  }
}
