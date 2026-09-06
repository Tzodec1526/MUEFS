import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { getErrorDetail } from '../../utils/errors';
import { getDemoCourtId, type SessionProfile } from '../auth/LoginScreen';
import LoadError from '../common/LoadError';

type Assignment = NonNullable<SessionProfile['court_assignments']>[number];
interface Directory {
  cases: { id: number; case_number: string; title: string; is_sealed: boolean; status: string }[];
  next_before_id: number | null;
}

export default function CourtCaseDirectory() {
  const [courts, setCourts] = useState<Assignment[]>([]);
  const [court, setCourt] = useState<number>();
  const [caseNumber, setCaseNumber] = useState('');
  const [cursors, setCursors] = useState<(number | undefined)[]>([undefined]);
  const [attempt, setAttempt] = useState(0);
  const [profileError, setProfileError] = useState('');
  const [result, setResult] = useState<{ key: string; data?: Directory; error?: string }>();
  const cursor = cursors[cursors.length - 1];
  const key = `${court}:${caseNumber}:${cursor}:${attempt}`;
  const current = result?.key === key ? result : undefined;

  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<SessionProfile>('/auth/me', { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      const assignments = (data.court_assignments || []).filter(item => ['clerk', 'judge', 'admin'].includes(item.role));
      const distinct = [...new Map(assignments.map(item => [item.court_id, item])).values()];
      setCourts(distinct);
      setCourt(previous => distinct.some(item => item.court_id === previous) ? previous
        : distinct.find(item => item.court_id === getDemoCourtId())?.court_id ?? distinct[0]?.court_id);
      setProfileError(distinct.length ? '' : 'A staff assignment is required to use the court case directory.');
    }).catch(err => {
      if (!controller.signal.aborted) setProfileError(getErrorDetail(err) || 'Could not load court assignments.');
    });
    return () => controller.abort();
  }, [attempt]);

  useEffect(() => {
    if (!court) return;
    const controller = new AbortController();
    apiClient.get<Directory>('/clerk/cases', {
      params: { court_id: court, case_number: caseNumber || undefined, before_id: cursor }, signal: controller.signal,
    }).then(({ data }) => {
      if (!controller.signal.aborted) setResult({ key, data });
    }).catch(err => {
      if (!controller.signal.aborted) setResult({ key, error: getErrorDetail(err) || 'Could not load court cases.' });
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
    <div className="page-header"><h2>Court cases</h2></div>
    <p>Find public and sealed cases at your assigned courts. Participant records and access changes are available from each case.</p>
    {profileError && <LoadError message={profileError} onRetry={() => setAttempt(n => n + 1)} />}
    <form className="court-case-filter" onSubmit={search}>
      <div className="form-group"><label htmlFor="directory-court">Court</label>
        <select id="directory-court" value={court ?? ''} onChange={event => {
          setCourt(Number(event.target.value)); setCursors([undefined]);
        }} disabled={!courts.length}>
          {!courts.length && <option value="">Loading assignments…</option>}
          {courts.map(item => <option key={item.court_id} value={item.court_id}>{item.court_name || `Court ${item.court_id}`}</option>)}
        </select></div>
      <div className="form-group"><label htmlFor="directory-case-number">Exact case number (optional)</label>
        <input id="directory-case-number" name="case_number" maxLength={50} placeholder="Leave blank to browse" /></div>
      <button className="btn btn-primary" disabled={!court}>Find cases</button>
    </form>
    {court && !current && <p role="status">Loading court cases…</p>}
    {current?.error && <LoadError message={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      {!current.data.cases.length && <p>No cases match this court and case number.</p>}
      <ul className="court-case-list">{current.data.cases.map(item => <li key={item.id}>
        <div><Link to={`/cases/${item.id}`}><strong>{item.case_number}</strong> — {item.title}</Link>
          <p>{item.status} {item.is_sealed && '· Sealed'}</p></div>
        <Link className="btn btn-secondary btn-small" to={`/cases/${item.id}/participants`}>Manage participants</Link>
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
