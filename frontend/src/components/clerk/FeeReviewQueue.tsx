import { useContext, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { CourtContext, StaffCourtSelect } from '../auth/CourtSession';
import { parseServerDate } from '../../utils/format';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import LoadError from '../common/LoadError';
import { usePageTitle } from '../../utils/pageTitle';

interface Queue { total: number; page: number; filings: { id: number; case_title: string | null; filer_name: string; status: string; requested_at: string }[] }

export default function FeeReviewQueue() {
  const { court } = useContext(CourtContext)!;
  usePageTitle('Fee reviews', court?.court_name);
  const courtId = court!.court_id;
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: Queue; error?: LoadFailure }>();
  const key = `${courtId}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<Queue>('/clerk/fee-reviews', { params: { court_id: courtId, page }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load fee review requests.') }); });
    return () => controller.abort();
  }, [courtId, page, key]);
  return <section>
    <StaffCourtSelect />
    <div className="page-header"><div><h2>Court fee reviews</h2><p>Requests awaiting an itemized assessment.</p></div>
      <button className="btn btn-secondary" onClick={() => setAttempt(n => n + 1)}>Refresh requests</button></div>
    <p>Reviewing fees does not submit or accept a filing. Fee waiver applications follow their separate court procedure.</p>
    {!current && <p role="status">Loading fee review requests…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      {!current.data.total && <p className="empty-state">No fee review requests are waiting.</p>}
      {current.data.filings.map(filing => <article className="review-card" key={filing.id}>
        <h3>Filing #{filing.id}: {filing.case_title || 'Untitled filing'}</h3>
        <p>{filing.filer_name} · {filing.status.replace(/_/g, ' ')} · Requested {parseServerDate(filing.requested_at).toLocaleString()}</p>
        <Link className="btn btn-primary" to={`/filings/${filing.id}/fees`}>Review fees</Link>
      </article>)}
      {current.data.total > 25 && <nav className="pagination" aria-label="Fee review pages">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous</button>
        <span>Page {page} of {Math.ceil(current.data.total / 25)}</span>
        <button className="btn btn-secondary" disabled={page * 25 >= current.data.total} onClick={() => setPage(n => n + 1)}>Next</button>
      </nav>}
    </>}
  </section>;
}
