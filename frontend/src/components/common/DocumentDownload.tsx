import { useState } from 'react';
import { apiClient } from '../../api/client';
import { errorMessage, getBlobErrorDetail } from '../../utils/errors';

export default function DocumentDownload({ id, title, copyId, deliveryId }: { id: number; title: string; copyId?: number | null; deliveryId?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      // Use the authenticated client: ordinary links cannot carry an OIDC bearer token.
      const path = deliveryId ? `/service/deliveries/${deliveryId}/documents/${id}`
        : copyId ? `/document-public-copies/${copyId}/download` : `/documents/${id}/download`;
      const { data, headers } = await apiClient.get<Blob>(path, { responseType: 'blob' });
      const url = URL.createObjectURL(data);
      const link = document.createElement('a');
      link.href = url;
      const filename = /filename\*=UTF-8''([^;]+)/i.exec(String(headers['content-disposition'] || ''));
      link.download = filename ? decodeURIComponent(filename[1]) : title;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      // A failed integrity check is permanent; do not present it as a transient error.
      setError(await getBlobErrorDetail(err) || errorMessage(err, 'Download unavailable. Please retry.'));
    } finally {
      setBusy(false);
    }
  }

  return <span className="document-download">
    <button type="button" className="btn btn-small btn-secondary" disabled={busy}
      aria-label={`Download ${title}`} onClick={download}>{busy ? 'Downloading…' : 'Download'}</button>
    {error && <span className="download-error" role="alert">{error}</span>}
  </span>;
}
