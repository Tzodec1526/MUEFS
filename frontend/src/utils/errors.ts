/** Pull the FastAPI/axios error detail string out of an unknown error, if present. */
export function getErrorDetail(err: unknown): string | undefined {
  return (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
}
