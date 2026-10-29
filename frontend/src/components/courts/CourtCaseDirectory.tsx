import { useContext, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import { CourtContext, StaffCourtSelect } from '../auth/CourtSession';
import LoadError from '../common/LoadError';

interface Directory {
  cases: { id: number; case_number: string; title: string; is_sealed: boolean; status: string }[];
  next_before_id: number | null;
}

export default function CourtCaseDirectory() {
  const { court: assignment } = useContext(CourtContext)!;
  const court = assignment!.court_id;
  const [caseNumber, setCaseNumber] = useState('');
  const [cursors, setCursors] = useState<(number | undefined)[]>([undefined]);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: Directory; error?: LoadFailure }>();
  const cursor = cursors[cursors.length - 1];
  const key = `${court}:${caseNumber}:${cursor}:${attempt}`;
  const current = result?.key === key ? result : undefined;

  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<Directory>('/clerk/cases', {
      params: { court_id: court, case_number: caseNumber || undefined, before_id: cursor }, signal: controller.signal,
    }).then(({ data }) => {
      if (!controller.signal.aborted) setResult({ key, data });
    }).catch(err => {
      if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load court cases.') });
    });
    return () => controller.abort();
  }, [court, caseNumber, cursor, key]);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCaseNumber(String(new FormData(event.currentTarget).get('case_number') || '').trim());
    setCursors([undefined]);
    setAttempt(n => n + 1);
  }

  return <section className="court-cases-page">
    <StaffCourtSelect />
    <div className="page-header"><h2>Court cases</h2></div>
    <p>Find public and sealed cases at your assigned courts. Participant records and access changes are available from each case.</p>
    <form className="court-case-filter" onSubmit={search}>
      <div className="form-group"><label htmlFor="directory-case-number">Exact case number (optional)</label>
        <input id="directory-case-number" name="case_number" maxLength={50} placeholder="Leave blank to browse" /></div>
      <button className="btn btn-primary">Find cases</button>
    </form>
    {!current && <p role="status">Loading court cases…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      {!current.data.cases.length && <p>No cases match this court and case number.</p>}
      <ul className="court-case-list">{current.data.cases.map(item => <li key={item.id}>
        <div><Link to={`/cases/${item.id}`}><strong>{item.case_number}</strong> — {item.title}</Link>
          <p>{item.status} {item.is_sealed && '· Sealed'}</p></div>
        <Link className="btn btn-secondary btn-small" to={`/cases/${item.id}/participants`}>Manage case access</Link>
      </li>)}</ul>
      <nav className="pagination" aria-label="Court case pages">
        <button className="btn btn-secondary" disabled={cursors.length === 1} onClick={() => setCursors(items => items.slice(0, -1))}>Previous cases</button>
        <span>Page {cursors.length}</span>
        <button className="btn btn-secondary" disabled={current.data.next_before_id == null} onClick={() => {
          const next = current.data?.next_before_id;
          if (next != null) setCursors(items => [...items, next]);
        }}>Next cases</button>
      </nav>
    </>}
  </section>;
}
