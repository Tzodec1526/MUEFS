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

export function errorStatus(err: unknown): number | undefined {
  const status = (err as { response?: { status?: unknown } })?.response?.status;
  return typeof status === 'number' ? status : undefined;
}

export function errorMessage(err: unknown, fallback: string): string {
  const status = errorStatus(err);
  return getErrorDetail(err)
    || (status === 429 ? 'Too many requests. Please wait a moment and try again.'
      : status === 403 ? 'You do not have permission to do that.' : fallback);
}

export interface LoadFailure { message: string; retry: boolean }

export function loadFailure(err: unknown, fallback: string): LoadFailure {
  const status = errorStatus(err);
  return { message: errorMessage(err, fallback), retry: status !== 401 && status !== 403 };
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
