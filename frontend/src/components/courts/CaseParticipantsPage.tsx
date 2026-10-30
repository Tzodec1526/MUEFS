import { useEffect, useState, type FormEvent } from 'react';
import { isAxiosError } from 'axios';
import { Link, useParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { participantRoles } from '../../api/cases';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { formatDateTime } from '../../utils/format';
import LoadError from '../common/LoadError';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

interface Participant {
  id: number; party_name: string; role: string; account_email: string | null; user_id: number | null;
  attorney_bar_number: string | null; represented_party_name: string | null;
  is_active: boolean; access_enabled: boolean; reviewed_at: string | null;
}
interface Records {
  case_number: string; title: string; is_sealed: boolean; participant_version: number;
  actor_id: number; participants: Participant[]; total: number;
}
interface History {
  total: number; events: { id: number; action: string; occurred_at: string; details: {
    actor_name?: string; reason?: string; authority_reference?: string;
    before?: Record<string, unknown>; after?: Record<string, unknown>;
  } }[];
}
const fields: Record<string, string> = {
  party_name: 'Name', role: 'Role', user_id: 'Linked account', attorney_bar_number: 'Bar number',
  represented_party_name: 'Represented party', is_active: 'Active participant', access_enabled: 'Restricted-case access',
  is_sealed: 'Public case access restricted',
};

function ParticipantForm({ caseId, record, version, onSaved }: {
  caseId: string; record?: Participant; version: number; onSaved: () => void;
}) {
  const [role, setRole] = useState(record?.role || 'defendant');
  const [active, setActive] = useState(record?.is_active ?? true);
  const [access, setAccess] = useState(record?.access_enabled || false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const counsel = role.startsWith('attorney');
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError('');
    const data = {
      party_name: form.get('party_name'), role, account_email: form.get('account_email') || null,
      attorney_bar_number: counsel ? form.get('attorney_bar_number') || null : null,
      represented_party_name: counsel ? form.get('represented_party_name') || null : null,
      is_active: active, access_enabled: access, expected_version: version, reason: form.get('reason'),
    };
    try {
      if (record) await apiClient.put(`/cases/${caseId}/participants/${record.id}`, data);
      else await apiClient.post(`/cases/${caseId}/participants`, data);
      onSaved();
    } catch (err) { setError(errorMessage(err, 'Could not save the participant record.')); }
    finally { setBusy(false); }
  }
  return <form className="admin-account-form" onSubmit={save}>
    <h3>{record ? 'Edit participant' : 'Add participant'}</h3>
    {record && !record.reviewed_at && <p className="alert alert-info">This legacy record requires court review before it can grant restricted-case access.</p>}
    <div className="admin-form-grid">
      <div className="form-group"><label htmlFor="participant-name">Participant name</label>
        <input id="participant-name" name="party_name" required maxLength={255} defaultValue={record?.party_name} /></div>
      <div className="form-group"><label htmlFor="participant-role">Recorded role</label>
        <select id="participant-role" value={role} onChange={event => setRole(event.target.value)}>
          {Object.entries(participantRoles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></div>
    </div>
    {counsel && <div className="admin-form-grid">
      <div className="form-group"><label htmlFor="participant-bar">Attorney bar number</label>
        <input id="participant-bar" name="attorney_bar_number" maxLength={20} required={access} defaultValue={record?.attorney_bar_number || ''} /></div>
      <div className="form-group"><label htmlFor="participant-represented">Represented party</label>
        <input id="participant-represented" name="represented_party_name" maxLength={255} defaultValue={record?.represented_party_name || ''} /></div>
    </div>}
    <div className="form-group"><label htmlFor="participant-account">Linked account email (optional unless granting access)</label>
      <input id="participant-account" name="account_email" type="email" maxLength={255} required={access} defaultValue={record?.account_email || ''} />
      <p className="info-text">Use an existing account. Counsel access also requires its matching verified bar number.</p></div>
    <label className="checkbox-label"><input type="checkbox" checked={active} onChange={event => {
      setActive(event.target.checked); if (!event.target.checked) setAccess(false);
    }} /> Active participant</label>
    <label className="checkbox-label"><input type="checkbox" checked={access} disabled={!active} onChange={event => setAccess(event.target.checked)} />
      Grant restricted-case access through this record</label>
    <p>Retire a participant by clearing “Active participant.” Other active grants or court roles can still allow access. Filers keep access to their own envelopes.</p>
    <div className="form-group"><label htmlFor="participant-reason">Reason and court authority or record reference</label>
      <textarea id="participant-reason" name="reason" required maxLength={1000} rows={3} /></div>
    {error && <p className="alert alert-error" role="alert">{error}</p>}
    <button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save participant'}</button>
  </form>;
}

function PublicAccessForm({ caseId, restricted, version, onSaved, onReload }: {
  caseId: string; restricted: boolean; version: number; onSaved: () => void; onReload: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [mustReload, setMustReload] = useState(false);
  const [error, setError] = useState('');
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || mustReload) return;
    const values = new FormData(event.currentTarget);
    setBusy(true); setError('');
    try {
      await apiClient.put(`/cases/${caseId}/public-access`, {
        expected_version: version, is_sealed: !restricted,
        confirm_public_release: values.get('confirm_public_release') === 'on',
        reason: values.get('reason'), authority_reference: values.get('authority_reference'),
      });
      onSaved();
    } catch (err) {
      const status = isAxiosError(err) ? err.response?.status : undefined;
      setMustReload(!status || status >= 500 || [401, 403, 409].includes(status));
      setError(errorMessage(err, 'The change could not be confirmed. Reload the records and review history before trying again.'));
    } finally { setBusy(false); }
  }
  return <details className="admin-detail-section">
    <summary>Change public case access</summary>
    <form className="admin-account-form" onSubmit={save}>
      <p>Record an instruction authorized by the court. This changes access throughout this portal; it does not issue a sealing order.
        Use document-level public access controls when an instruction applies only to particular documents.</p>
      <p>{restricted
        ? 'Restoring public access exposes the case number, title, party names, and accepted records allowed by their existing document settings. Review those settings and the court’s authority before proceeding.'
        : 'Restricting public access removes this case from public search and blocks public docket and document requests. Authorized staff, explicit participant grants, and filers’ access to their own records remain.'}</p>
      <fieldset disabled={busy || mustReload}>
        <legend>{restricted ? 'Restore public case access' : 'Restrict public case access'}</legend>
        <div className="form-group"><label htmlFor="case-access-authority">Authority or order reference</label>
          <input id="case-access-authority" name="authority_reference" maxLength={500} required /></div>
        <div className="form-group"><label htmlFor="case-access-reason">Reason for this change</label>
          <textarea id="case-access-reason" name="reason" rows={3} maxLength={1000} required /></div>
        {restricted && <label className="checkbox-label"><input type="checkbox" name="confirm_public_release" required />
          I verified the court&apos;s instruction to restore public access and reviewed the current document settings.</label>}
        <button className="btn btn-primary" type="submit">{busy ? 'Saving…' : restricted ? 'Restore public access' : 'Restrict public access'}</button>
      </fieldset>
      {busy && <p role="status">Saving the court&apos;s access instruction…</p>}
      {error && <div className="alert alert-error" role="alert"><p>{error}</p>
        {mustReload && <><p>Review the current records and history before another change. Reloading replaces this form.</p>
          <button className="btn btn-secondary" type="button" onClick={onReload}>Reload case access records</button></>}
      </div>}
    </form>
  </details>;
}

function ParticipantHistory({ caseId }: { caseId: string }) {
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: History; error?: LoadFailure }>();
  const key = `${caseId}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<History>(`/cases/${caseId}/participants/history`, { params: { page }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load case access history.') }); });
    return () => controller.abort();
  }, [caseId, page, key]);
  function display(value: unknown, field: string) {
    if (value == null) return 'Not set';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (field === 'role') return participantRoles[String(value)] || String(value);
    return field === 'user_id' ? `Account ${value}` : String(value);
  }
  return <section className="admin-detail-section">
    <h3>Retained case access history</h3>
    {!current && <p role="status">Loading history…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      {!current.data.total && <p>No case access changes recorded.</p>}
      <ol className="admin-history">{current.data.events.map(event => <li key={event.id}>
        <strong>{event.action === 'case.participant_created' ? 'Participant added'
          : event.action === 'case.participant_changed' ? 'Participant changed'
          : event.action === 'case.public_access_changed' ? 'Public case access changed' : 'Legacy records require review'}
          {event.details.after?.party_name ? ` · ${event.details.after.party_name}` : ''}</strong>
        <p>{formatDateTime(event.occurred_at)} · {event.details.actor_name || 'Database migration'}</p>
        <p>{event.details.reason}</p>
        {event.details.authority_reference && <p>Authority: {event.details.authority_reference}</p>}
        {event.details.after && <details><summary>View recorded changes</summary><dl className="admin-changes">{Object.entries(fields).filter(([field]) =>
          event.details.before?.[field] !== event.details.after?.[field],
        ).map(([field, label]) => <div key={field}><dt>{label}</dt><dd>
          {display(event.details.before?.[field], field)} → {display(event.details.after?.[field], field)}
        </dd></div>)}</dl></details>}
      </li>)}</ol>
      {current.data.total > 25 && <nav className="pagination" aria-label="Case access history pages">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous changes</button>
        <span>Page {page} of {Math.ceil(current.data.total / 25)}</span>
        <button className="btn btn-secondary" disabled={page * 25 >= current.data.total} onClick={() => setPage(n => n + 1)}>Next changes</button>
      </nav>}
    </>}
  </section>;
}

export default function CaseParticipantsPage() {
  usePageTitle('Case access and participants');
  const { caseId = '' } = useParams<{ caseId: string }>();
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [selection, setSelection] = useState<number | 'new' | null>(null);
  const [notice, setNotice] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [result, setResult] = useState<{ key: string; data?: Records; error?: LoadFailure }>();
  const key = `${caseId}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  const selected = current?.data?.participants.find(item => item.id === selection);
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<Records>(`/cases/${caseId}/participants`, { params: { page }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load participants.') }); });
    return () => controller.abort();
  }, [caseId, page, key]);
  const editor = current?.data && (selection === 'new' || selected) && <ParticipantForm
    key={`${caseId}:${selection}:${current.data.participant_version}`} caseId={caseId}
    record={selected} version={current.data.participant_version} onSaved={() => {
      setSelection(null); setNotice('Participant record saved.'); setAttempt(n => n + 1);
    }} />;
  return <section className="case-participants-page">
    <div className="page-header"><PageHeading>Case access and participants</PageHeading><Link to={`/cases/${caseId}`} className="btn btn-secondary">Back to case</Link></div>
    {!current && <p role="status">Loading participant records…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      <h3>{current.data.case_number} · {current.data.title}</h3>
      <p><strong>{current.data.is_sealed ? 'Public case access is restricted.' : 'Public case access is enabled.'}</strong></p>
      <PublicAccessForm key={`${caseId}:${current.data.participant_version}`} caseId={caseId}
        restricted={current.data.is_sealed} version={current.data.participant_version}
        onSaved={() => { setSelection(null); setNotice('Public case access instruction recorded.'); setAttempt(n => n + 1); }}
        onReload={() => { setSelection(null); setNotice(''); setAttempt(n => n + 1); }} />
      <p>Record court-authorized participation and portal access. Saving a participant record does not file an appearance, approve withdrawal, or enroll anyone in electronic service.</p>
      {notice && <p className="alert alert-success" role="status">{notice}</p>}
      <div className="participant-actions">
        <button className="btn btn-primary" onClick={() => { setSelection('new'); setNotice(''); }}>Add participant</button>
        <button className="btn btn-secondary" onClick={() => { setSelection(null); setNotice(''); setAttempt(n => n + 1); }}>Refresh records</button>
      </div>
      {selection === 'new' && editor}
      <ul className="court-case-list participant-list">{current.data.participants.map(item => <li key={item.id}>
        <div><strong>{item.party_name}</strong><p>{participantRoles[item.role] || item.role} · {item.is_active ? 'Active' : 'Former'}
          {' · '}{item.access_enabled ? 'Access granted through this record' : 'No access grant'}</p>
          {item.represented_party_name && <p>Represents {item.represented_party_name}</p>}
          {item.account_email && <p>{item.account_email}</p>}
          {!item.reviewed_at && <p>Legacy record · court review needed</p>}</div>
        {item.user_id === current.data?.actor_id ? <span>Another staff member must edit your record.</span>
          : <button className="btn btn-secondary btn-small" onClick={() => { setSelection(item.id); setNotice(''); }}
            aria-label={`Edit ${item.party_name}`}>Edit</button>}
        <Link className="btn btn-secondary btn-small" to={`/cases/${caseId}/participants/${item.id}/service-contact`}
          aria-label={`Service instructions for ${item.party_name}`}>Service instructions</Link>
        {selection === item.id && editor}
      </li>)}</ul>
      {!current.data.total && <p>No participants recorded.</p>}
      {current.data.total > 25 && <nav className="pagination" aria-label="Participant pages">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => { setPage(n => n - 1); setSelection(null); }}>Previous participants</button>
        <span>Page {page} of {Math.ceil(current.data.total / 25)}</span>
        <button className="btn btn-secondary" disabled={page * 25 >= current.data.total} onClick={() => { setPage(n => n + 1); setSelection(null); }}>Next participants</button>
      </nav>}
      <button className="btn btn-secondary" onClick={() => setShowHistory(value => !value)} aria-expanded={showHistory}>
        {showHistory ? 'Hide case access history' : 'View case access history'}</button>
      {showHistory && <ParticipantHistory key={`${caseId}:${attempt}`} caseId={caseId} />}
    </>}
  </section>;
}
