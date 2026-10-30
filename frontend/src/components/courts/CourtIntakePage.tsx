import { useContext, useEffect, useState, type FormEvent } from 'react';
import { isAxiosError } from 'axios';
import { Link, useParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { formatDateTime } from '../../utils/format';
import { CourtContext } from '../auth/CourtSession';
import LoadError from '../common/LoadError';
import '../../styles/intake.css';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';
import PageLoadError from '../common/PageLoadError';

interface IntakeState {
  court_id: number; court_name: string; version: number;
  is_efiling_enabled: boolean; public_notice: string | null;
  case_types: { id: number; code: string; name: string; is_active: boolean }[];
}
interface Intake extends IntakeState { can_manage: boolean }
interface Change {
  id: number; timestamp: string; actor_name: string; reason: string; authority_reference: string;
  before: IntakeState; after: IntakeState;
}
interface History { changes: Change[]; total: number }
interface Remote<T> { key: string; data?: T; error?: LoadFailure }

function IntakeEditor({ current, onSaved, onReload }: {
  current: Intake; onSaved: (value: Intake) => void; onReload: () => void;
}) {
  const [enabled, setEnabled] = useState(current.is_efiling_enabled);
  const [notice, setNotice] = useState(current.public_notice || '');
  const [types, setTypes] = useState(current.case_types.map(item => ({ id: item.id, is_active: item.is_active })));
  const [reason, setReason] = useState('');
  const [authority, setAuthority] = useState('');
  const [busy, setBusy] = useState(false);
  const [mustReload, setMustReload] = useState(false);
  const [error, setError] = useState('');
  const changed = enabled !== current.is_efiling_enabled || notice.trim() !== (current.public_notice || '')
    || types.some((item, index) => item.is_active !== current.case_types[index].is_active);
  const needsNotice = !enabled || types.some(item => !item.is_active);

  async function publish(event: FormEvent) {
    event.preventDefault();
    if (busy || mustReload || !changed) return;
    setBusy(true); setError('');
    try {
      const { data } = await apiClient.put<Intake>(`/courts/${current.court_id}/intake`, {
        expected_version: current.version, is_efiling_enabled: enabled,
        public_notice: notice.trim() || null, case_types: types,
        reason: reason.trim(), authority_reference: authority.trim(),
      });
      onSaved(data);
    } catch (err) {
      const status = isAxiosError(err) ? err.response?.status : undefined;
      const reload = !status || status >= 500 || [401, 403, 409].includes(status);
      setMustReload(reload);
      setError(errorMessage(err, 'The change could not be confirmed. Reload current settings and review the history before trying again.'));
    } finally { setBusy(false); }
  }

  return <form onSubmit={publish} className="intake-editor">
    <p>Closing intake stops new submissions and corrections. Received filings remain available for court review.
      Court calendars and filing-date orders are managed separately.</p>
    <fieldset disabled={busy || mustReload}>
      <legend>Settings to publish</legend>
      <label className="intake-checkbox"><input type="checkbox" checked={enabled}
        onChange={event => setEnabled(event.target.checked)} /> Enable electronic intake for this court</label>
      <fieldset className="intake-case-settings"><legend>Case types enabled for electronic intake</legend>
        <p>These selections are retained while the court&apos;s intake is closed.</p>
        {current.case_types.map((item, index) => <label className="intake-checkbox" key={item.id}>
          <input type="checkbox" checked={types[index].is_active} onChange={event => {
            const active = event.target.checked;
            setTypes(items => items.map(entry => entry.id === item.id ? { ...entry, is_active: active } : entry));
          }} /> {item.name} ({item.code})
        </label>)}
      </fieldset>
      <div className="form-group"><label htmlFor="intake-notice">Public intake notice{needsNotice ? ' (required)' : ' (optional)'}</label>
        <textarea id="intake-notice" rows={4} maxLength={2000} required={needsNotice}
          value={notice} onChange={event => setNotice(event.target.value)} aria-describedby="intake-notice-help" />
        <p id="intake-notice-help">Published publicly. Explain how filers should proceed when intake is closed; omit private case information.</p>
      </div>
      <div className="form-group"><label htmlFor="intake-reason">Reason for this change</label>
        <textarea id="intake-reason" rows={2} maxLength={2000} required value={reason}
          onChange={event => setReason(event.target.value)} /></div>
      <div className="form-group"><label htmlFor="intake-authority">Authority or operational reference</label>
        <input id="intake-authority" maxLength={300} required value={authority}
          onChange={event => setAuthority(event.target.value)} aria-describedby="intake-history-help" />
        <p id="intake-history-help">The reason and authority are retained in the administrator-only change history.</p>
      </div>
      <button className="btn btn-primary" type="submit" disabled={!changed || !reason.trim() || !authority.trim() || (needsNotice && !notice.trim())}>
        {busy ? 'Publishing…' : 'Publish intake settings'}</button>
    </fieldset>
    {busy && <p role="status">Publishing intake settings…</p>}
    {error && <div className="alert alert-error" role="alert"><p>{error}</p>
      {mustReload && <><p>Review the latest settings before making another change. Reloading replaces the form above.</p>
        <button type="button" className="btn btn-secondary" onClick={onReload}>Reload current settings</button></>}
    </div>}
  </form>;
}

function IntakeHistory({ courtId }: { courtId: number }) {
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Remote<History>>();
  const key = `${courtId}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<History>(`/courts/${courtId}/intake/history`, { params: { page }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load intake changes.') }); });
    return () => controller.abort();
  }, [courtId, page, key]);
  return <section aria-label="Intake change history">
    <h3>Intake change history</h3>
    {!current && <p role="status">Loading intake changes…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      {current.data.total === 0 && <p>No intake changes have been published through this portal. Existing settings are shown above.</p>}
      {current.data.changes.map(change => {
        const previous = new Map(change.before.case_types.map(item => [item.id, item.is_active]));
        const typeChanges = change.after.case_types.filter(item => previous.get(item.id) !== item.is_active);
        return <article className="review-card" key={change.id}>
          <h4>Revision {change.after.version} · {change.actor_name}</h4>
          <p>{formatDateTime(change.timestamp)}</p>
          <p><strong>Reason:</strong> {change.reason}</p>
          <p><strong>Authority:</strong> {change.authority_reference}</p>
          {change.before.is_efiling_enabled !== change.after.is_efiling_enabled && <p>
            Court intake {change.after.is_efiling_enabled ? 'opened' : 'closed'}.</p>}
          {typeChanges.length > 0 && <ul>{typeChanges.map(item => <li key={item.id}>
            {item.name}: {item.is_active ? 'enabled' : 'disabled'}</li>)}</ul>}
          {change.before.public_notice !== change.after.public_notice && <details>
            <summary>Compare public notices</summary>
            <p><strong>Previous notice</strong></p><p className="intake-notice">{change.before.public_notice || 'No notice'}</p>
            <p><strong>Published notice</strong></p><p className="intake-notice">{change.after.public_notice || 'No notice'}</p>
          </details>}
        </article>;
      })}
      {current.data.total > 25 && <nav className="pagination" aria-label="Intake change pages">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous changes</button>
        <span>Page {page} of {Math.ceil(current.data.total / 25)}</span>
        <button className="btn btn-secondary" disabled={page * 25 >= current.data.total} onClick={() => setPage(n => n + 1)}>Next changes</button>
      </nav>}
    </>}
  </section>;
}

export default function CourtIntakePage() {
  const { courtId } = useParams();
  const { userId, loading } = useContext(CourtContext)!;
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Remote<Intake>>();
  const [message, setMessage] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const key = `${courtId}:${userId ?? 'public'}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  usePageTitle(current && !current.data ? 'Filing intake not loaded' : 'Filing intake', current?.data?.court_name);
  useEffect(() => {
    if (loading) return;
    const controller = new AbortController();
    apiClient.get<Intake>(`/courts/${courtId}/intake`, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load court intake information.') }); });
    return () => controller.abort();
  }, [courtId, key, loading]);
  if (loading || !current) return <p role="status">Loading court intake…</p>;
  if (!current.data) {
    return <PageLoadError heading="Filing intake not loaded"
      failure={current.error ?? { message: 'Could not load intake.', retry: true }} onRetry={() => setAttempt(n => n + 1)} />;
  }
  const data = current.data;
  return <section className="court-intake-page">
    <div className="page-header"><div><PageHeading>{data.court_name}: electronic filing intake</PageHeading>
      <p>Current availability and instructions published by the court.</p></div>
      <Link className="btn btn-secondary" to={`/courts/${data.court_id}/calendar`}>Court calendar</Link></div>
    <div className="review-card">
      <h3>{data.is_efiling_enabled ? 'Court intake enabled' : 'Court intake closed'}</h3>
      {!data.is_efiling_enabled && <p>New electronic submissions and corrections are currently unavailable.</p>}
      {(data.public_notice || !data.is_efiling_enabled) && <>
        <h4>Notice from the court</h4>
        <p className="intake-notice">{data.public_notice || 'Contact the court for filing options.'}</p>
      </>}
      <p>For deadlines or alternative filing arrangements, follow the court&apos;s instructions.</p>
      <table className="intake-table"><thead><tr><th scope="col">Case type</th><th scope="col">Electronic intake</th></tr></thead>
        <tbody>{data.case_types.map(item => <tr key={item.id}>
          <td>{item.name} <span className="text-muted">({item.code})</span></td>
          <td>{data.is_efiling_enabled && item.is_active ? 'Accepting filings' : 'Not accepting filings'}</td>
        </tr>)}</tbody></table>
      {data.case_types.length === 0 && <p>No case types are available for electronic filing.</p>}
    </div>
    {data.can_manage && <>
      {message && <p className="alert alert-success" role="status">{message}</p>}
      <details className="review-card"><summary>Manage electronic intake</summary>
        <IntakeEditor key={data.version} current={data} onSaved={saved => {
          setResult({ key, data: saved }); setMessage(`Intake revision ${saved.version} published. The previous settings remain in the change history.`);
        }} onReload={() => { setAttempt(n => n + 1); setMessage(''); }} />
      </details>
      <button className="btn btn-secondary" onClick={() => setShowHistory(value => !value)} aria-expanded={showHistory}>
        {showHistory ? 'Hide change history' : 'View change history'}</button>
      {showHistory && <IntakeHistory key={`${userId}:${data.version}`} courtId={data.court_id} />}
    </>}
  </section>;
}
