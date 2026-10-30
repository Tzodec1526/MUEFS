import { useContext, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { deliveryLabels, listNotifications, type NotificationItem } from '../../api/notifications';
import { CourtContext, StaffCourtSelect } from '../auth/CourtSession';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { formatDateTime } from '../../utils/format';
import LoadError from '../common/LoadError';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

interface DeliveryHistory {
  events: { id: number; attempt_number: number; outcome: string; occurred_at: string;
    detail: string | null; smtp_code: number | null }[];
  total: number; page: number; message_id: string | null; can_retry: boolean;
}

function DeliveryDetails({ notice, onRetry }: { notice: NotificationItem; onRetry: () => void }) {
  const [result, setResult] = useState<{ key: string; data?: DeliveryHistory; error?: LoadFailure }>();
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const requestKey = `${notice.id}:${page}:${attempt}`;
  const current = result?.key === requestKey ? result : undefined;
  const history = current?.data;
  const error = current?.error;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<DeliveryHistory>(`/notifications/${notice.id}/delivery`, { params: { page }, signal: controller.signal })
      .then(response => { if (!controller.signal.aborted) setResult({ key: requestKey, data: response.data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key: requestKey, error: loadFailure(err, 'Could not load email history.') }); });
    return () => controller.abort();
  }, [notice.id, page, requestKey]);

  async function retry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setBusy(true); setActionError(null);
    try {
      await apiClient.post(`/notifications/${notice.id}/retry`, { reason: values.get('reason') });
      onRetry();
    } catch (err) { setActionError(errorMessage(err, 'Could not queue another email.')); }
    finally { setBusy(false); }
  }

  return <div className="notice-delivery">
    <h3 className="card-subheading">Email history for notice #{notice.id}</h3>
    {error && <LoadError failure={error} onRetry={() => setAttempt(n => n + 1)} />}
    {!history && !error && <p role="status">Loading email history…</p>}
    {history && <>
      {history.message_id && <p className="receipt-reference">Message-ID: <code>{history.message_id}</code></p>}
      {history.events.length === 0 && <p>No email attempts have been recorded.</p>}
      <ol>{history.events.map(event => <li key={event.id}>
        <strong>{event.outcome.replace(/_/g, ' ')}</strong> · Attempt {event.attempt_number} ·{' '}
        <time dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)}</time>
        {event.smtp_code != null && <span> · SMTP {event.smtp_code}</span>}
        {event.detail && <p>{event.detail}</p>}
      </li>)}</ol>
      {history.total > 25 && <nav className="pagination" aria-label="Email history pages">
        <button className="btn btn-secondary btn-small" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous attempts</button>
        <span>Page {page} of {Math.ceil(history.total / 25)}</span>
        <button className="btn btn-secondary btn-small" disabled={page * 25 >= history.total} onClick={() => setPage(n => n + 1)}>Next attempts</button>
      </nav>}
      {(notice.delivery_status === 'unknown' || notice.delivery_status === 'legacy') && <p className="alert alert-warning">The message may already have reached the relay.
        Court staff should check its records before requesting another email.</p>}
      {history.can_retry && <form onSubmit={retry}>
        <div className="form-group"><label htmlFor={`retry-${notice.id}`}>Reason for requesting another email</label>
          <input id={`retry-${notice.id}`} name="reason" maxLength={1000} required /></div>
        {actionError && <p className="alert alert-error" role="alert">{actionError}</p>}
        <button className="btn btn-secondary" disabled={busy}>{busy ? 'Queuing…' : 'Queue another email'}</button>
      </form>}
    </>}
  </div>;
}

export default function NotificationsPage() {
  usePageTitle('Notices and email status');
  const { court, loading: assignmentsLoading } = useContext(CourtContext)!;
  const courtId = court?.court_id;
  const staff = courtId != null;
  const [scopeChoice, setScope] = useState('court');
  const scope = staff ? scopeChoice : 'mine';
  const [status, setStatus] = useState('');
  const [filingId, setFilingId] = useState<number>();
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: Awaited<ReturnType<typeof listNotifications>>; error?: LoadFailure }>();
  const [selected, setSelected] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const requestKey = `${page}:${scope}:${courtId}:${status}:${filingId}:${attempt}`;
  const current = result?.key === requestKey ? result : undefined;
  const data = current?.data;
  const error = current?.error;
  const loading = !current;
  useEffect(() => {
    if (assignmentsLoading) return;
    const controller = new AbortController();
    listNotifications(page, { court_id: scope === 'court' && courtId ? courtId : undefined,
      delivery_status: status || undefined, filing_id: filingId }, controller.signal)
      .then(data => { if (!controller.signal.aborted) setResult({ key: requestKey, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key: requestKey, error: loadFailure(err, 'Could not load notices.') }); });
    return () => controller.abort();
  }, [page, scope, courtId, status, filingId, requestKey, assignmentsLoading]);

  return <section className="notices-page">
    {staff && scope === 'court' && <StaffCourtSelect disabled={selected != null} onChange={() => {
      setPage(1); setSelected(null); setMessage('');
    }} />}
    <div className="page-header"><div><PageHeading>Notices &amp; email status</PageHeading>
      <p>Read filing updates and track email attempts.</p></div>
      <button className="btn btn-secondary" onClick={() => setAttempt(n => n + 1)}>Refresh notices</button></div>
    <p>Updates remain available in the portal even when email fails. Acceptance by an email relay does not confirm inbox delivery or legal service.</p>
    <div className="calendar-range">
      {staff && <div className="form-group"><label htmlFor="notice-scope">Notice scope</label>
        <select id="notice-scope" value={scope} onChange={event => { setScope(event.target.value); setPage(1); setSelected(null); }}>
          <option value="court">Court filing notices</option><option value="mine">My notices</option>
        </select></div>}
      <div className="form-group"><label htmlFor="notice-status">Email status</label>
        <select id="notice-status" value={status} onChange={event => { setStatus(event.target.value); setPage(1); setSelected(null); }}>
          <option value="">All statuses</option>
          {Object.entries(deliveryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></div>
    </div>
    <form className="calendar-range notice-filing-filter" onSubmit={event => {
      event.preventDefault();
      const value = String(new FormData(event.currentTarget).get('filing_id') || '').trim();
      setFilingId(value ? Number(value) : undefined); setPage(1); setSelected(null); setMessage('');
    }}>
      <div className="form-group"><label htmlFor="notice-filing">Filing number</label>
        <input id="notice-filing" name="filing_id" type="number" min="1" max="2147483647" step="1"
          placeholder="For example, 123" aria-describedby="notice-filing-help" /></div>
      <button className="btn btn-primary" type="submit">Find notices</button>
      <button className="btn btn-secondary" type="reset" onClick={() => {
        setFilingId(undefined); setPage(1); setSelected(null); setMessage('');
      }}>Clear filing filter</button>
    </form>
    <p id="notice-filing-help">Search by the filing number shown on a receipt. Scope and email status filters still apply.</p>
    {filingId != null && <p role="status">Showing notices for filing #{filingId}.</p>}
    {message && <p role="status" className="alert alert-success">{message}</p>}
    {loading && <p role="status">Loading notices…</p>}
    {error && <LoadError failure={error} onRetry={() => setAttempt(n => n + 1)} />}
    {!loading && !error && data && <>
      {!data.email_enabled && <p className="alert alert-warning">Email delivery is not enabled. These notices are available in the portal.</p>}
      <p>{data.total} notice{data.total === 1 ? '' : 's'}</p>
      {data.notifications.map(notice => <article className="review-card notice-card" key={notice.id}>
        <h2 className="card-heading">{notice.subject}</h2>
        <p className="notice-body">{notice.body}</p>
        <p><strong>{deliveryLabels[notice.delivery_status] || notice.delivery_status}</strong> · {notice.attempt_count} email attempt{notice.attempt_count === 1 ? '' : 's'}</p>
        {notice.email_recipient && <p>Recipient: {notice.email_recipient}</p>}
        {notice.last_error && <p className="alert alert-warning">{notice.last_error}</p>}
        {notice.delivery_status === 'sent' && notice.sent_at && <p>Relay acceptance recorded: {formatDateTime(notice.sent_at)}</p>}
        {notice.next_attempt_at && <p>Next attempt: {formatDateTime(notice.next_attempt_at)}</p>}
        <div className="history-summary">
          {notice.delivery_id ? <Link to={`/service/deliveries/${notice.delivery_id}`}>Open document delivery</Link>
            : notice.filing_envelope_id && <Link to={`/filings/${notice.filing_envelope_id}/history`}>View filing history</Link>}
          <button className="btn btn-secondary btn-small" aria-expanded={selected === notice.id}
            onClick={() => setSelected(selected === notice.id ? null : notice.id)}>Email history</button>
        </div>
        {selected === notice.id && <DeliveryDetails notice={notice} key={`${notice.id}-${notice.delivery_status}-${notice.attempt_count}`}
          onRetry={() => { setAttempt(n => n + 1); setMessage('Another email has been queued. Earlier attempts are retained.'); }} />}
      </article>)}
      {data.total > data.page_size && <nav className="pagination" aria-label="Notice pages">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => { setPage(n => n - 1); setSelected(null); }}>Previous notices</button>
        <span>Page {page} of {Math.ceil(data.total / data.page_size)}</span>
        <button className="btn btn-secondary" disabled={page * data.page_size >= data.total} onClick={() => { setPage(n => n + 1); setSelected(null); }}>Next notices</button>
      </nav>}
    </>}
  </section>;
}
