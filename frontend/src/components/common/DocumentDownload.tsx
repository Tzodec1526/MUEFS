import { useState } from 'react';
import { apiClient } from '../../api/client';

export default function DocumentDownload({ id, title, copyId }: { id: number; title: string; copyId?: number | null }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  async function download() {
    setBusy(true);
    setError(false);
    try {
      // Use the authenticated client: ordinary links cannot carry an OIDC bearer token.
      const path = copyId ? `/document-public-copies/${copyId}/download` : `/documents/${id}/download`;
      const { data, headers } = await apiClient.get<Blob>(path, { responseType: 'blob' });
      const url = URL.createObjectURL(data);
      const link = document.createElement('a');
      link.href = url;
      const filename = /filename\*=UTF-8''([^;]+)/i.exec(String(headers['content-disposition'] || ''));
      link.download = filename ? decodeURIComponent(filename[1]) : title;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return <span className="document-download">
    <button type="button" className="btn btn-small btn-secondary" disabled={busy}
      aria-label={`Download ${title}`} onClick={download}>{busy ? 'Downloading…' : 'Download'}</button>
    {error && <span className="download-error" role="alert">Download unavailable. Please retry.</span>}
  </span>;
}
