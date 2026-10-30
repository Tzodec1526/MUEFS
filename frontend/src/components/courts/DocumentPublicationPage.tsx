import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { formatBytes, parseServerDate } from '../../utils/format';
import DocumentDownload from '../common/DocumentDownload';
import LoadError from '../common/LoadError';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

interface PublicCopy {
  id: number; document_id: number; title: string; file_size_bytes: number; sha256_hash: string;
  page_count: number; pii_warnings: string[]; created_at: string;
}
interface Publication {
  document: { id: number; title: string; sha256_hash: string; is_confidential: boolean; file_size_bytes: number };
  filing_id: number; case_id: number | null; filing_status: string; version: number;
  current_copy: PublicCopy | null; copies: PublicCopy[]; total: number;
  publication_block: string | null; can_withhold: boolean;
}
interface History {
  total: number; events: { id: number; action: string; occurred_at: string; actor_name: string;
    details: { title?: string; copy_id?: number; reason?: string; before?: { public_copy_id: number | null; original_restricted: boolean } };
  }[];
}

function PublicationHistory({ documentId }: { documentId: string }) {
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: History; error?: LoadFailure }>();
  const key = `${documentId}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<History>(`/clerk/documents/${documentId}/publication/history`, { params: { page }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load access history.') }); });
    return () => controller.abort();
  }, [documentId, page, key]);
  const labels: Record<string, string> = {
    'document.public_copy_prepared': 'Public copy prepared', 'public_copy.published': 'Public copy published',
    'document.withheld': 'Document withheld from public access',
  };
  return <>
    {!current && <p role="status">Loading document access history…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      {!current.data.total && <p>No access changes recorded.</p>}
      <ol className="admin-history">{current.data.events.map(event => <li key={event.id}>
        <strong>{labels[event.action] || event.action}</strong>
        <p>{parseServerDate(event.occurred_at).toISOString().replace('T', ' ').replace('Z', ' UTC')} · {event.actor_name}</p>
        {event.details.title && <p>{event.details.title}</p>}
        {event.details.reason && <p>{event.details.reason}</p>}
        {event.details.before && <p>Before this change: original {event.details.before.original_restricted ? 'restricted' : 'available through the case docket'}
          {event.details.before.public_copy_id ? `; public copy ${event.details.before.public_copy_id} active` : '; no public copy active'}.</p>}
      </li>)}</ol>
      {current.data.total > 25 && <nav className="pagination" aria-label="Document access history pages">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous changes</button>
        <span>Page {page} of {Math.ceil(current.data.total / 25)}</span>
        <button className="btn btn-secondary" disabled={page * 25 >= current.data.total} onClick={() => setPage(n => n + 1)}>Next changes</button>
      </nav>}
    </>}
  </>;
}

export default function DocumentPublicationPage() {
  usePageTitle('Document public access');
  const { documentId = '' } = useParams<{ documentId: string }>();
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: Publication; error?: LoadFailure }>();
  const [candidate, setCandidate] = useState<PublicCopy>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
  const [copiesOpen, setCopiesOpen] = useState(false);
  const key = `${documentId}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  const selected = candidate?.document_id === Number(documentId) ? candidate : undefined;
  const reviewHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    reviewHeading.current?.focus();
  }, [selected?.id, current?.data?.version]);
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<Publication>(`/clerk/documents/${documentId}/publication`, { params: { page }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load document access.') }); });
    return () => controller.abort();
  }, [documentId, page, key]);

  async function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true); setError(''); setNotice('');
    try {
      const { data } = await apiClient.post<PublicCopy>(`/clerk/documents/${documentId}/public-copies`, new FormData(form), {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setCandidate(data); form.reset(); setAttempt(n => n + 1);
      setNotice('Copy prepared for review. It has not been published.');
    } catch (err) { setError(errorMessage(err, 'Could not prepare the copy.')); }
    finally { setBusy(false); }
  }
  async function change(event: FormEvent<HTMLFormElement>, publish: boolean) {
    event.preventDefault();
    if (!current?.data) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(''); setNotice('');
    try {
      await apiClient.post(`/clerk/documents/${documentId}/${publish ? 'publication' : 'withhold'}`, {
        expected_version: current.data.version, reason: form.get('reason'),
        ...(publish ? { copy_id: selected?.id, reviewed: form.has('reviewed') } : {}),
      });
      setCandidate(undefined); setAttempt(n => n + 1);
      setNotice(publish ? 'Public copy published. The original remains restricted.' : 'Original and public copy withheld from public access.');
    } catch (err) { setError(errorMessage(err, 'Could not change document access.')); }
    finally { setBusy(false); }
  }
  return <section className="document-publication-page">
    <div className="page-header"><PageHeading>Document public access</PageHeading>
      <button className="btn btn-secondary" disabled={busy} onClick={() => {
        setCandidate(undefined); setError(''); setNotice(''); setAttempt(n => n + 1);
      }}>Refresh document</button></div>
    {!current && <p role="status">Loading document access…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {notice && <p className="alert alert-success" role="status">{notice}</p>}
    {error && <p className="alert alert-error" role="alert">{error}</p>}
    {current?.data && <>
      <Link to={`/filings/${current.data.filing_id}/history`}>Back to filing receipts &amp; history</Link>
      <div className="publication-grid">
        <section className="review-card"><h3>Filed original</h3><p><strong>{current.data.document.title}</strong></p>
          <p>{formatBytes(current.data.document.file_size_bytes)} · {current.data.filing_status}</p>
          <p>{current.data.document.is_confidential ? 'Restricted to the filer and assigned court staff.' : 'Available through the case docket, subject to case access.'}</p>
          <DocumentDownload id={current.data.document.id} title={current.data.document.title} />
          <details><summary>Original fingerprint</summary><code>{current.data.document.sha256_hash}</code></details>
        </section>
        <section className="review-card"><h3>Active public copy</h3>
          {current.data.current_copy ? <><p><strong>{current.data.current_copy.title}</strong></p>
            <p>{formatBytes(current.data.current_copy.file_size_bytes)} · {current.data.current_copy.page_count} page{current.data.current_copy.page_count === 1 ? '' : 's'}</p>
            <DocumentDownload id={current.data.document.id} copyId={current.data.current_copy.id} title={current.data.current_copy.title} />
          </> : <p>No public copy is active.</p>}
          <p>Case restrictions still apply. Earlier copies and the original are retained.</p>
        </section>
      </div>
      {current.data.can_withhold && <form className="review-card" key={`withhold:${documentId}:${current.data.version}`} onSubmit={event => change(event, false)}>
        <h3>Withhold public access</h3>
        <p>Use the court&apos;s authority to withhold the original and any active public copy while review is pending. Previously downloaded files cannot be recalled.</p>
        <div className="form-group"><label htmlFor="withhold-reason">Reason and authority for withholding</label>
          <textarea id="withhold-reason" name="reason" maxLength={2000} required rows={2} /></div>
        <button className="btn btn-secondary" disabled={busy}>Withhold document</button>
      </form>}
      {current.data.publication_block ? <p className="alert alert-info">{current.data.publication_block}</p> : <>
        <form className="review-card" onSubmit={prepare} key={`prepare:${documentId}`}>
          <h3>Prepare a public copy</h3>
          <p>Upload a court-reviewed PDF with the required redactions. Preparation retains a separate copy for review; the original and its receipt stay intact.</p>
          <div className="form-group"><label htmlFor="public-title">Title approved for the public docket</label>
            <input id="public-title" name="title" maxLength={500} required /></div>
          <div className="form-group"><label htmlFor="public-pdf">Public copy PDF</label>
            <input id="public-pdf" name="file" type="file" accept="application/pdf,.pdf" required /></div>
          <button className="btn btn-secondary" disabled={busy}>{busy ? 'Working…' : 'Prepare copy for review'}</button>
        </form>
        {selected && <form className="review-card" key={`review:${documentId}:${selected.id}:${current.data.version}`} onSubmit={event => change(event, true)}>
          <h3 ref={reviewHeading} tabIndex={-1}>Review prepared copy</h3><p><strong>{selected.title}</strong> · {selected.page_count} page{selected.page_count === 1 ? '' : 's'} · {formatBytes(selected.file_size_bytes)}</p>
          <DocumentDownload id={current.data.document.id} copyId={selected.id} title={selected.title} />
          <details><summary>Prepared copy fingerprint</summary><code>{selected.sha256_hash}</code></details>
          {selected.pii_warnings.length > 0 && <div className="alert alert-warning"><strong>Review these scan warnings before publishing:</strong>
            <ul>{selected.pii_warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></div>}
          <p>The scan samples text and cannot prove redaction is complete. Review the entire PDF, hidden text, annotations and metadata using the court&apos;s approved tools.</p>
          <label className="publication-confirm"><input type="checkbox" name="reviewed" required />
            I reviewed this exact PDF and its public title and confirmed they may be released under the authority recorded below.</label>
          <div className="form-group"><label htmlFor="publication-reason">Reason and authority for publication</label>
            <textarea id="publication-reason" name="reason" maxLength={2000} required rows={3} /></div>
          <button className="btn btn-primary" disabled={busy}>Publish reviewed copy</button>
        </form>}
      </>}
      <details className="review-card" open={copiesOpen} onToggle={event => setCopiesOpen(event.currentTarget.open)}>
        <summary>Prepared and earlier copies ({current.data.total})</summary>
        <ul className="court-case-list">{current.data.copies.map(copy => <li key={copy.id}>
          <div><strong>{copy.title}</strong><p>Copy {copy.id} · {copy.page_count} page{copy.page_count === 1 ? '' : 's'} · {formatBytes(copy.file_size_bytes)}
            {copy.id === current.data?.current_copy?.id && ' · Active'}</p></div>
          <div className="participant-actions"><DocumentDownload id={Number(documentId)} copyId={copy.id} title={copy.title} />
            {!current.data?.publication_block && <button className="btn btn-secondary btn-small" disabled={busy} onClick={() => { setCandidate(copy); setError(''); }}>Review this copy</button>}</div>
        </li>)}</ul>
        {current.data.total > 25 && <nav className="pagination" aria-label="Public copy pages">
          <button className="btn btn-secondary" disabled={page === 1 || busy} onClick={() => setPage(n => n - 1)}>Previous copies</button>
          <span>Page {page} of {Math.ceil(current.data.total / 25)}</span>
          <button className="btn btn-secondary" disabled={page * 25 >= current.data.total || busy} onClick={() => setPage(n => n + 1)}>Next copies</button>
        </nav>}
      </details>
      <details className="review-card" open={historyOpen} onToggle={event => setHistoryOpen(event.currentTarget.open)}>
        <summary>Retained access history</summary>
        {historyOpen && <PublicationHistory key={`${documentId}:${attempt}`} documentId={documentId} />}
      </details>
    </>}
  </section>;
}
