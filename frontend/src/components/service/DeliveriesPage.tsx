import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { deliveryLabels } from '../../api/notifications';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import { parseServerDate } from '../../utils/format';
import LoadError from '../common/LoadError';

interface DeliveryList {
  deliveries: { id: string; name?: string; email?: string; actor_name?: string; created_at: string; delivery_status: string }[];
  total: number;
  page_size: number;
}

export default function DeliveriesPage() {
  const { filingId } = useParams();
  const location = useLocation();
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: DeliveryList; error?: LoadFailure }>();
  const key = `${filingId}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<DeliveryList>(filingId ? `/service/filings/${filingId}/deliveries` : '/service/deliveries', { params: { page }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load deliveries.') }); });
    return () => controller.abort();
  }, [filingId, page, key]);
  const data = current?.data;
  return <section className="service-page">
    <div className="page-header"><div><h2>{filingId ? `Filing #${filingId}: document deliveries` : 'Document delivery inbox'}</h2>
      <p>{filingId ? 'Selected recipients and their retained delivery records.' : 'Document packages addressed to your account.'}</p></div>
      <button className="btn btn-secondary" onClick={() => setAttempt(n => n + 1)}>Refresh deliveries</button></div>
    {filingId && <div className="service-actions"><Link to={`/filings/${filingId}/history`}>Filing history</Link>
      <Link className="btn btn-primary" to={`/filings/${filingId}/deliveries/new`}>Select documents &amp; recipients</Link></div>}
    {location.state?.sent && <p className="alert alert-success" role="status">Delivery recorded and email alerts queued. Open a recipient record to check progress.</p>}
    <p>Email relay acceptance, document download requests and recipient acknowledgments are recorded separately. Follow the court&apos;s requirements for proof of service.</p>
    {!current && <p role="status">Loading deliveries…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {data && <>
      {!data.deliveries.length && <p className="empty-state">No document deliveries recorded.</p>}
      <ul className="service-list">{data.deliveries.map(item => <li className="review-card" key={item.id}>
        <h3><Link to={`/service/deliveries/${item.id}`}>{item.name || `Documents from ${item.actor_name}`}</Link></h3>
        {item.email && <p>{item.email}</p>}
        <p><time dateTime={item.created_at}>{parseServerDate(item.created_at).toLocaleString()}</time></p>
        <p>{deliveryLabels[item.delivery_status] || item.delivery_status}</p>
      </li>)}</ul>
      {data.total > data.page_size && <nav className="pagination" aria-label="Delivery pages">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous deliveries</button>
        <span>Page {page} of {Math.ceil(data.total / data.page_size)}</span>
        <button className="btn btn-secondary" disabled={page * data.page_size >= data.total} onClick={() => setPage(n => n + 1)}>Next deliveries</button>
      </nav>}
    </>}
  </section>;
}
