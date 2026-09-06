import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { deliveryLabels } from '../../api/notifications';
import type { DeliveryDetails } from '../../api/serviceDeliveries';
import { getErrorDetail } from '../../utils/errors';
import { formatBytes, parseServerDate } from '../../utils/format';
import DocumentDownload from '../common/DocumentDownload';
import LoadError from '../common/LoadError';

interface EventList {
  events: { id: number; action: string; occurred_at: string; actor_name?: string; detail?: string;
    details?: { document_id?: number; reason?: string }; smtp_code?: number; attempt_number?: number }[];
  total: number; page_size: number;
}

function DeliveryHistory({ deliveryId }: { deliveryId: string }) {
  const [kind, setKind] = useState('portal');
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: EventList; error?: string }>();
  const key = `${deliveryId}:${kind}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<EventList>(`/service/deliveries/${deliveryId}/events`, { params: { kind, page }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: getErrorDetail(err) || 'Could not load delivery history.' }); });
    return () => controller.abort();
  }, [deliveryId, kind, page, key]);
  return <div className="review-card"><h3>Retained delivery history</h3>
    <label htmlFor="delivery-history-kind">Records to display</label>
    <select id="delivery-history-kind" value={kind} onChange={event => { setKind(event.target.value); setPage(1); }}>
      <option value="portal">Document requests &amp; acknowledgments</option><option value="email">Email attempts</option>
    </select>
    {!current && <p role="status">Loading history…</p>}
    {current?.error && <LoadError message={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      {!current.data.events.length && <p>No events of this type recorded.</p>}
      <ol>{current.data.events.map(event => <li key={event.id}>
        <strong>{event.action.replace(/_/g, ' ')}</strong> · <time dateTime={event.occurred_at}>{parseServerDate(event.occurred_at).toISOString().replace('T', ' ').replace('Z', ' UTC')}</time>
        {event.actor_name && <span> · {event.actor_name}</span>}
        {event.attempt_number != null && <span> · Attempt {event.attempt_number}</span>}
        {event.smtp_code != null && <span> · SMTP {event.smtp_code}</span>}
        {event.details?.document_id != null && <p>Document #{event.details.document_id}</p>}
        {(event.detail || event.details?.reason) && <p>{event.detail || event.details?.reason}</p>}
      </li>)}</ol>
      {current.data.total > current.data.page_size && <nav className="pagination" aria-label="Delivery history pages">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous events</button>
        <span>Page {page} of {Math.ceil(current.data.total / current.data.page_size)}</span>
        <button className="btn btn-secondary" disabled={page * current.data.page_size >= current.data.total} onClick={() => setPage(n => n + 1)}>Next events</button>
      </nav>}
    </>}
  </div>;
}

export default function DeliveryDetailPage() {
  const { deliveryId } = useParams();
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: DeliveryDetails; error?: string }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState(false);
  const key = `${deliveryId}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  const data = current?.data;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<DeliveryDetails>(`/service/deliveries/${deliveryId}`, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: getErrorDetail(err) || 'Could not open this delivery.' }); });
    return () => controller.abort();
  }, [deliveryId, key]);

  async function act(action: 'acknowledge' | 'retry', reason?: string) {
    setBusy(true); setError('');
    try {
      await apiClient.post(`/service/deliveries/${deliveryId}/${action}`, reason ? { reason } : undefined);
      setAttempt(n => n + 1);
    } catch (err) { setError(getErrorDetail(err) || 'Could not record this action.'); }
    finally { setBusy(false); }
  }

  function retry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void act('retry', String(new FormData(event.currentTarget).get('reason')));
  }

  return <section className="service-page">
    <div className="page-header"><div><h2>Document delivery record</h2><p>Contents and evidence for this named recipient.</p></div>
      <Link className="btn btn-secondary" to="/service/deliveries">Delivery inbox</Link></div>
    {!current && <p role="status">Loading delivery…</p>}
    {current?.error && <LoadError message={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {error && <p role="alert" className="alert alert-error">{error}</p>}
    {data && <>
      <div className="review-card"><h3>{data.court_name}</h3><p>{data.case_number} · {data.case_title}</p>
        <p>From {data.sender} to {data.contact.name} · {data.contact.email}</p>
        <p>Recorded {parseServerDate(data.created_at).toLocaleString()}</p>
        <p>Service authority: {data.contact.authority}</p>
        <p className="receipt-reference">Delivery reference: <code>{data.id}</code></p>
      </div>
      <div className="review-card"><h3>Documents in this delivery</h3>
        <ul className="service-list">{data.documents.map(doc => <li className="service-choice" key={doc.id}>
          <h4>{doc.title}</h4><p>{formatBytes(doc.file_size_bytes)}{doc.is_confidential && ' · Confidential'}</p>
          <DocumentDownload id={doc.id} title={doc.title} deliveryId={data.id} />
          <details><summary>Retained document fingerprint</summary><code>{doc.sha256_hash}</code></details>
        </li>)}</ul>
        {data.acknowledged_at ? <p className="alert alert-success">Recipient acknowledged this package on {parseServerDate(data.acknowledged_at).toLocaleString()}.</p>
          : <p>No recipient acknowledgment recorded.</p>}
        {data.can_acknowledge && <button className="btn btn-primary" disabled={busy} onClick={() => void act('acknowledge')}>Acknowledge receipt of this package</button>}
        <p>An acknowledgment records the recipient&apos;s statement. A download request records a request, and does not establish that the transfer completed.</p>
      </div>
      <div className="review-card"><h3>Email alert</h3><p>{deliveryLabels[data.delivery_status] || data.delivery_status}</p>
        {data.last_error && <p className="alert alert-warning">{data.last_error}</p>}
        <p>Relay acceptance does not confirm inbox delivery or completed legal service. Follow the court&apos;s requirements for proof of service.</p>
        {data.message_id && <p className="receipt-reference">Message-ID: <code>{data.message_id}</code></p>}
        {(data.delivery_status === 'unknown' || data.delivery_status === 'legacy') && <p className="alert alert-warning">Court staff must check the uncertain outcome before requesting another alert.</p>}
        {data.can_retry && <form onSubmit={retry}><div className="form-group"><label htmlFor="delivery-retry-reason">Reason for requesting another alert</label>
          <input id="delivery-retry-reason" name="reason" required maxLength={1000} disabled={busy} /></div>
          <button className="btn btn-secondary" disabled={busy}>Queue another alert</button></form>}
        <button className="btn btn-secondary" disabled={busy} onClick={() => setAttempt(n => n + 1)}>Refresh delivery status</button>
      </div>
      <button className="btn btn-secondary" aria-expanded={history} onClick={() => setHistory(value => !value)}>{history ? 'Hide delivery history' : 'Show delivery history'}</button>
      {history && <DeliveryHistory key={key} deliveryId={data.id} />}
    </>}
  </section>;
}
