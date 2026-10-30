import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import type { DeliveryContact, DeliveryOptions } from '../../api/serviceDeliveries';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { formatBytes } from '../../utils/format';
import DocumentDownload from '../common/DocumentDownload';
import LoadError from '../common/LoadError';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

export default function DeliveryComposePage() {
  const { filingId } = useParams();
  usePageTitle('Send documents', `Filing #${filingId}`);
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: DeliveryOptions; error?: LoadFailure }>();
  const [selection, setSelection] = useState<{ source: string; documents: number[]; contacts: DeliveryContact[] }>({ source: '', documents: [], contacts: [] });
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<{ body: string; key: string }>();
  const key = `${filingId}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  const data = current?.data;

  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<DeliveryOptions>(`/service/filings/${filingId}/options`, { params: { page }, signal: controller.signal })
      .then(({ data }) => {
        if (controller.signal.aborted) return;
        setResult({ key, data });
        setSelection(previous => previous.source === data.source_transaction_id ? previous : {
          source: data.source_transaction_id, documents: [], contacts: [],
        });
        setReviewed(false);
      })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load delivery choices.') }); });
    return () => controller.abort();
  }, [filingId, page, key]);

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!data || busy) return;
    const body = JSON.stringify({ source_transaction_id: selection.source,
      document_ids: [...selection.documents].sort((a, b) => a - b),
      recipients: selection.contacts.map(c => ({ contact_id: c.contact_id!, version: c.version! })).sort((a, b) => a.contact_id - b.contact_id),
      reviewed: true,
    });
    if (request.current?.body !== body) request.current = { body, key: crypto.randomUUID() };
    setBusy(true); setError('');
    try {
      await apiClient.post(`/service/filings/${filingId}/deliveries`, body, {
        headers: { 'Idempotency-Key': request.current.key },
      });
      navigate(`/filings/${filingId}/deliveries`, { state: { sent: true } });
    } catch (err) {
      setError(errorMessage(err, 'The request could not be confirmed. Retry these selections to retrieve the same delivery, or inspect the sent records.'));
    } finally { setBusy(false); }
  }

  return <section className="service-page">
    <div className="page-header"><div><PageHeading>Send documents</PageHeading>
      <p>Filing #{filingId} · Subsequent documents on an existing case</p></div>
      <Link className="btn btn-secondary" to={`/filings/${filingId}/deliveries`}>Delivery records</Link></div>
    <p>Select the documents and recipients required by the court&apos;s service instructions. Case-initiating service and recipients who require mail or hand delivery use the applicable procedure outside this workflow.</p>
    <button className="btn btn-secondary" disabled={busy} onClick={() => {
      setSelection({ source: '', documents: [], contacts: [] }); setReviewed(false); setError(''); setAttempt(n => n + 1);
    }}>Refresh choices</button>
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {!current && <p role="status">Loading documents and service instructions…</p>}
    {data && <>
      <div className="review-card"><h2 className="card-heading">{data.court_name}</h2><p>{data.case_number} · {data.case_title}</p></div>
      {!data.enabled && <p className="alert alert-warning">Document delivery is not enabled for this deployment. Follow the court&apos;s service instructions.</p>}
      {error && <p role="alert" className="alert alert-error">{error}</p>}
      <form onSubmit={send}>
        <fieldset disabled={busy || !data.enabled}>
          <legend>Documents to include</legend>
          <p>Only the checked documents will be available to the selected accounts. Fee-waiver documents are excluded.</p>
          {!data.documents.length && <p>No eligible documents were retained in this submission.</p>}
          {data.documents.map(doc => <div className="service-choice" key={doc.id}>
            <label className="checkbox-label"><input type="checkbox" checked={selection.documents.includes(doc.id)}
              onChange={event => { setReviewed(false); setSelection(s => ({ ...s, documents: event.target.checked ? [...s.documents, doc.id] : s.documents.filter(id => id !== doc.id) })); }} />
              <span><strong>{doc.title}</strong> · {formatBytes(doc.file_size_bytes)}
                {doc.is_confidential && <span className="status-badge">Confidential — review recipient authority</span>}</span></label>
            <DocumentDownload id={doc.id} title={doc.title} />
          </div>)}
          <h2 className="card-heading">Recipients and service instructions</h2>
          <p>{data.total} active case participant{data.total === 1 ? '' : 's'}. Review every page for people who need another service method.</p>
          {data.recipients.map(contact => <div className="service-choice" key={contact.participant_id}>
            <label className="checkbox-label"><input type="checkbox" disabled={contact.issues.length > 0}
              checked={selection.contacts.some(c => c.contact_id === contact.contact_id && c.participant_id === contact.participant_id)}
              onChange={event => { setReviewed(false); setSelection(s => ({ ...s, contacts: event.target.checked ? [...s.contacts, contact] : s.contacts.filter(c => c.participant_id !== contact.participant_id) })); }} />
              <span><strong>{contact.name}</strong> · {contact.role.replace(/_/g, ' ')}
                {contact.represented_party_name && <span> · Represents {contact.represented_party_name}</span>}</span></label>
            <p>{contact.method?.replace(/_/g, ' ') || 'Instructions needed'} · {contact.email || contact.address || 'No destination recorded'}</p>
            {contact.authority && <p>Authority: {contact.authority}</p>}
            {contact.issues.map(issue => <p className="service-issue" key={issue}>{issue}</p>)}
          </div>)}
          {data.total > data.page_size && <nav className="pagination" aria-label="Service participant pages">
            <button type="button" className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous participants</button>
            <span>Page {page} of {Math.ceil(data.total / data.page_size)}</span>
            <button type="button" className="btn btn-secondary" disabled={page * data.page_size >= data.total} onClick={() => setPage(n => n + 1)}>Next participants</button>
          </nav>}
          <div className="review-card"><h2 className="card-heading">Review this delivery</h2>
            <p>{selection.documents.length} document{selection.documents.length === 1 ? '' : 's'} · {selection.contacts.length} recipient{selection.contacts.length === 1 ? '' : 's'}</p>
            <ul>{selection.contacts.map(contact => <li key={contact.contact_id}>{contact.name} · {contact.email}
              {' '}<button type="button" className="btn btn-small btn-secondary" onClick={() => { setReviewed(false); setSelection(s => ({ ...s, contacts: s.contacts.filter(c => c.contact_id !== contact.contact_id) })); }}>Remove {contact.name}</button>
            </li>)}</ul>
            <label className="checkbox-label"><input type="checkbox" required checked={reviewed} onChange={event => setReviewed(event.target.checked)} />
              <span>I reviewed the selected contents, recipients and service authority. I will arrange any additional service required for this case.</span></label>
            <p>The portal retains the contents and queues a private email alert. A relay acknowledgment alone does not establish completed legal service.</p>
            {(selection.contacts.length > 100 || selection.documents.length > 100) && <p role="alert">Select at most 100 documents and 100 recipients per delivery.</p>}
            <button className="btn btn-primary" disabled={!reviewed || !selection.documents.length || !selection.contacts.length || selection.contacts.length > 100 || selection.documents.length > 100}>
              {busy ? 'Recording delivery…' : 'Record delivery & queue alerts'}</button>
          </div>
        </fieldset>
      </form>
    </>}
  </section>;
}
