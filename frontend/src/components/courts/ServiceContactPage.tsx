import { useContext, useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { participantRoles } from '../../api/cases';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { formatDateTime } from '../../utils/format';
import LoadError from '../common/LoadError';
import { CourtContext } from '../auth/CourtSession';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

const methods = { electronic: 'Electronic through portal', mail: 'Mail', hand_delivery: 'Hand delivery' };
interface Contact {
  id: number; name: string; method: keyof typeof methods; email: string | null;
  address: string | null; is_active: boolean; authority: string; version: number;
}
interface Instructions {
  court_id: number; case_number: string; title: string; participant_version: number;
  participant: { party_name: string; role: string; represented_party_name: string | null };
  verified_email: string | null; can_edit: boolean; contact: Contact | null; issues: string[];
}
interface History {
  total: number; events: { id: number; occurred_at: string; details: {
    actor_name: string; reason: string; before: Contact | null; after: Contact;
  } }[];
}

function ContactForm({ path, records, onSaved }: {
  path: string; records: Instructions; onSaved: () => void;
}) {
  const contact = records.contact;
  const [method, setMethod] = useState<keyof typeof methods>(contact?.method || 'electronic');
  const [active, setActive] = useState(contact?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError('');
    try {
      await apiClient.put(path, {
        method, is_active: active, email: method === 'electronic' ? form.get('email') : null,
        address: method === 'electronic' ? null : form.get('address'),
        authority: form.get('authority'), reason: form.get('reason'),
        expected_version: contact?.version || 0, expected_participant_version: records.participant_version,
      });
      onSaved();
    } catch (err) { setError(errorMessage(err, 'Could not save service instructions.')); }
    finally { setBusy(false); }
  }
  return <form className="admin-account-form" onSubmit={save}>
    <h2 className="card-heading">{contact ? 'Review service instructions' : 'Record service instructions'}</h2>
    <div className="form-group"><label htmlFor="service-method">Recorded service method</label>
      <select id="service-method" value={method} onChange={event => setMethod(event.target.value as keyof typeof methods)}>
        {Object.entries(methods).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></div>
    {method === 'electronic' ? <div className="form-group"><label htmlFor="service-email">Service email</label>
      <input id="service-email" name="email" type="email" required maxLength={255}
        defaultValue={contact?.email || records.verified_email || ''} />
      <p className="info-text">Use the participant’s verified account email. A portal account alone does not establish eligibility for electronic service.</p>
    </div> : <div className="form-group"><label htmlFor="service-address">Address and delivery instructions</label>
      <textarea id="service-address" name="address" required rows={3} maxLength={2000} defaultValue={contact?.address || ''} />
    </div>}
    <div className="form-group"><label htmlFor="service-authority">Court authority or source record</label>
      <textarea id="service-authority" name="authority" required rows={3} maxLength={1000} defaultValue={contact?.authority || ''} />
      <p className="info-text">Identify the registration, agreement, exemption, order or other reviewed record establishing these instructions, including any limits.</p></div>
    <label className="checkbox-label"><input type="checkbox" checked={active} onChange={event => setActive(event.target.checked)} />
      Active service instructions</label>
    <p>Clear this when the instructions are withdrawn, superseded or no longer authorized. Earlier instructions remain in history.</p>
    <div className="form-group"><label htmlFor="service-reason">Reason for this change</label>
      <textarea id="service-reason" name="reason" required rows={2} maxLength={1000} /></div>
    {error && <p className="alert alert-error" role="alert">{error}</p>}
    <button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save service instructions'}</button>
  </form>;
}

function ContactHistory({ path }: { path: string }) {
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: History; error?: LoadFailure }>();
  const key = `${path}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<History>(`${path}/history`, { params: { page }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load history.') }); });
    return () => controller.abort();
  }, [path, page, key]);
  return <section className="admin-delegations">
    {!current && <p role="status">Loading service history…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      {!current.data.total && <p>No service instructions have been recorded.</p>}
      <ul className="court-case-list">{current.data.events.map(event => <li key={event.id}>
        <div><strong>{formatDateTime(event.occurred_at)} · {event.details.actor_name}</strong>
          <p>{event.details.reason}</p>
          {event.details.before && <p>Previous: {methods[event.details.before.method]} · {event.details.before.email || event.details.before.address}
            {' · '}{event.details.before.is_active ? 'Active' : 'Inactive'}</p>}
          <p>Recorded: {methods[event.details.after.method]} · {event.details.after.email || event.details.after.address}
            {' · '}{event.details.after.is_active ? 'Active' : 'Inactive'}</p>
          <p>Authority: {event.details.after.authority}</p>
        </div></li>)}</ul>
      {current.data.total > 25 && <nav className="pagination" aria-label="Service history pages">
        <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous changes</button>
        <span>Page {page} of {Math.ceil(current.data.total / 25)}</span>
        <button className="btn btn-secondary" disabled={page * 25 >= current.data.total} onClick={() => setPage(n => n + 1)}>Next changes</button>
      </nav>}
    </>}
  </section>;
}

export default function ServiceContactPage() {
  usePageTitle('Service instructions');
  const { caseId, participantId } = useParams();
  const { courts } = useContext(CourtContext)!;
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
  const [result, setResult] = useState<{ key: string; data?: Instructions; error?: LoadFailure }>();
  const path = `/cases/${caseId}/participants/${participantId}/service-contact`;
  const key = `${path}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  const court = courts.find(item => item.court_id === current?.data?.court_id);
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<Instructions>(path, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load service instructions.') }); });
    return () => controller.abort();
  }, [path, key]);
  return <section className="case-participants-page">
    <div className="page-header"><PageHeading>Service instructions</PageHeading>
      <Link className="btn btn-secondary" to={`/cases/${caseId}/participants`}>Back to participants</Link></div>
    {!current && <p role="status">Loading service instructions…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      <h2 className="card-heading">{court?.court_name || `Court ${current.data.court_id}`} · {current.data.case_number} · {current.data.title}</h2>
      <p><strong>{current.data.participant.party_name}</strong> · {participantRoles[current.data.participant.role] || current.data.participant.role}
        {current.data.participant.represented_party_name && <> · Represents {current.data.participant.represented_party_name}</>}</p>
      <p>Record the court-reviewed destination and method for this participant. These instructions do not send documents or establish that service occurred.</p>
      {notice && <p className="alert alert-success" role="status">{notice}</p>}
      {current.data.issues.length > 0 && <div className="alert alert-warning"><strong>Review needed</strong>
        <ul>{current.data.issues.map(issue => <li key={issue}>{issue}</li>)}</ul></div>}
      {current.data.contact && !current.data.issues.length && <p className="alert alert-info">Current instructions: {methods[current.data.contact.method]} · {current.data.contact.email || current.data.contact.address}</p>}
      <button className="btn btn-secondary" onClick={() => { setNotice(''); setAttempt(n => n + 1); }}>Refresh instructions</button>
      {current.data.can_edit ? <ContactForm key={key} path={path} records={current.data} onSaved={() => {
        setNotice('Service instructions saved.'); setAttempt(n => n + 1);
      }} /> : <p>Another court staff member must manage your service instructions.</p>}
      <details onToggle={event => setHistoryOpen(event.currentTarget.open)}>
        <summary>Service instruction history</summary>
        {historyOpen && <ContactHistory key={key} path={path} />}
      </details>
    </>}
  </section>;
}
