import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { parseServerDate } from '../../utils/format';
import LoadError from '../common/LoadError';

interface Access {
  system_admin: boolean; user_id: number; courts: { id: number; name: string }[];
}
interface Account {
  id: number; first_name: string; last_name: string; email: string; user_type: string;
  is_active: boolean; administration_version: number; keycloak_id?: string | null;
  bar_number?: string | null; bar_number_verified?: boolean; email_verified?: boolean;
  court_roles: { court_id: number; court_name: string; role: string }[];
}
interface Directory { users: Account[]; total: number; page_size: number }
type Remote<T> = { key: string; data?: T; error?: LoadFailure };
const accountTypes: Record<string, string> = {
  attorney: 'Attorney', clerk: 'Court staff', judge: 'Judge', self_represented: 'Self-represented filer',
  public: 'Public records user', admin: 'System administrator',
};
const courtRoles: Record<string, string> = {
  clerk: 'Clerk review', judge: 'Judicial decisions', admin: 'Court administration', filer: 'Filer',
};

function AccountForm({ user, self, onSaved }: {
  user?: Account; self: boolean; onSaved: (user: Account) => void;
}) {
  const [kind, setKind] = useState(user?.user_type || 'clerk');
  const [verifiedBar, setVerifiedBar] = useState(user?.bar_number_verified || false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const data = {
      first_name: values.get('first_name'), last_name: values.get('last_name'), email: values.get('email'),
      user_type: kind, keycloak_id: (self ? user?.keycloak_id : values.get('keycloak_id')) || null,
      is_active: self || values.has('is_active'), bar_number: values.get('bar_number') || null,
      bar_number_verified: verifiedBar, reason: values.get('reason'),
      ...(user ? { expected_version: user.administration_version } : {}),
    };
    setBusy(true); setError('');
    try {
      const result = user ? await apiClient.put<Account>(`/admin/users/${user.id}`, data)
        : await apiClient.post<Account>('/admin/users', data);
      onSaved(result.data);
    } catch (err) { setError(errorMessage(err, 'Could not save the account.')); }
    finally { setBusy(false); }
  }
  return <form onSubmit={save} className="admin-account-form">
    <h3>{user ? 'Account identity' : 'Provision an account'}</h3>
    <p>Use the exact subject from the approved identity provider. Provisioning an account does not assign court access.</p>
    <div className="admin-form-grid">
      <div className="form-group"><label htmlFor="account-first">First name</label>
        <input id="account-first" name="first_name" maxLength={100} required defaultValue={user?.first_name} /></div>
      <div className="form-group"><label htmlFor="account-last">Last name</label>
        <input id="account-last" name="last_name" maxLength={100} required defaultValue={user?.last_name} /></div>
      <div className="form-group"><label htmlFor="account-email">Email address</label>
        <input id="account-email" name="email" type="email" maxLength={255} required defaultValue={user?.email} /></div>
      <div className="form-group"><label htmlFor="account-type">Account type</label>
        <select id="account-type" value={kind} disabled={self} onChange={event => { setKind(event.target.value); setVerifiedBar(false); }}>
          {Object.entries(accountTypes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></div>
    </div>
    <div className="form-group"><label htmlFor="account-subject">Identity provider subject</label>
      <input id="account-subject" name="keycloak_id" maxLength={255} disabled={self} defaultValue={user?.keycloak_id || ''} /></div>
    <label className="checkbox-label"><input name="is_active" type="checkbox" defaultChecked={user?.is_active ?? true} disabled={self} /> Account active</label>
    {self && <p>Another system administrator must change your own access or identity binding.</p>}
    <div className="form-group"><label htmlFor="account-bar">Bar number, if applicable</label>
      <input id="account-bar" name="bar_number" maxLength={20} defaultValue={user?.bar_number || ''} onChange={() => setVerifiedBar(false)} /></div>
    {kind === 'attorney' && <label className="checkbox-label"><input type="checkbox" checked={verifiedBar}
      onChange={event => setVerifiedBar(event.target.checked)} /> I verified this bar number using the court-approved source</label>}
    {user && <p>Email verification: {user.email_verified ? 'Recorded from the identity provider' : 'Not recorded for this address'}.</p>}
    <div className="form-group"><label htmlFor="account-reason">Reason and authority or reference for this change</label>
      <textarea id="account-reason" name="reason" rows={2} required maxLength={1000} /></div>
    {error && <p className="alert alert-error" role="alert">{error}</p>}
    <button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : user ? 'Save account' : 'Provision account'}</button>
  </form>;
}

function CourtAccess({ user, access, directoryCourt, onSaved }: {
  user: Account; access: Access; directoryCourt: number; onSaved: (user: Account) => void;
}) {
  const [court, setCourt] = useState(directoryCourt);
  const [role, setRole] = useState('clerk');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const granted = user.court_roles.some(grant => grant.court_id === court && grant.role === role);
  async function change(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true); setError('');
    try {
      const response = await apiClient.post<Account>(`/admin/courts/${court}/users/${user.id}/roles`, {
        role, action: granted ? 'revoke' : 'grant', expected_version: user.administration_version,
        reason: new FormData(form).get('reason'),
      });
      form.reset(); onSaved(response.data);
    } catch (err) { setError(errorMessage(err, 'Could not change court access.')); }
    finally { setBusy(false); }
  }
  return <section className="admin-detail-section">
    <h3>Court access</h3>
    {user.court_roles.length === 0 ? <p>No court roles assigned in this view.</p> : <ul>
      {user.court_roles.map(grant => <li key={`${grant.court_id}-${grant.role}`}>
        {grant.court_name}: <strong>{courtRoles[grant.role] || grant.role}</strong>
      </li>)}
    </ul>}
    {access.user_id === user.id ? <p>Another administrator must change your own court access.</p>
      : <form onSubmit={change}>
        <div className="admin-form-grid">
          <div className="form-group"><label htmlFor="access-court">Court for this change</label>
            <select id="access-court" value={court} disabled={!access.system_admin} onChange={event => setCourt(Number(event.target.value))}>
              {access.system_admin && <option value={0}>Choose a court</option>}
              {access.courts.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select></div>
          <div className="form-group"><label htmlFor="access-role">Court role</label>
            <select id="access-role" value={role} onChange={event => setRole(event.target.value)}>
              <option value="clerk">Clerk review</option><option value="judge">Judicial decisions</option>
              {access.system_admin && <option value="admin">Court administration</option>}
            </select></div>
        </div>
        {court !== 0 && <p>{granted ? 'Revoke' : 'Grant'} {courtRoles[role].toLowerCase()} for {user.first_name} {user.last_name} at {access.courts.find(item => item.id === court)?.name}.</p>}
        <div className="form-group"><label htmlFor="access-reason">Reason and authority for this court access change</label>
          <textarea id="access-reason" name="reason" rows={2} required maxLength={1000} /></div>
        {error && <p className="alert alert-error" role="alert">{error}</p>}
        <button className={`btn ${granted ? 'btn-secondary' : 'btn-primary'}`} disabled={busy || !court}>
          {busy ? 'Recording…' : granted ? 'Revoke court role' : 'Grant court role'}
        </button>
      </form>}
  </section>;
}

interface History {
  total: number; events: { id: number; action: string; occurred_at: string; details: {
    actor_name?: string; reason?: string; court_id?: number;
    before?: Record<string, unknown> | string[] | null; after?: Record<string, unknown> | string[] | null;
  } }[];
}
const historyLabels: Record<string, string> = {
  'identity.account_created': 'Account provisioned', 'identity.account_updated': 'Account changed',
  'identity.role_granted': 'Court role granted', 'identity.role_revoked': 'Court role revoked',
  'identity.bootstrap': 'Initial administrator provisioned',
  'identity.duplicate_role_removed': 'Duplicate historical grant archived',
};
const fieldLabels: Record<string, string> = {
  first_name: 'First name', last_name: 'Last name', email: 'Email address', user_type: 'Account type',
  keycloak_id: 'Identity subject', is_active: 'Account active', bar_number: 'Bar number', bar_number_verified: 'Bar verified',
};

function AccountHistory({ userId, courtId, access }: { userId: number; courtId?: number; access: Access }) {
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Remote<History>>();
  const key = `${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<History>(`/admin/users/${userId}/history`, { params: { page, court_id: courtId }, signal: controller.signal })
      .then(response => { if (!controller.signal.aborted) setResult({ key, data: response.data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load access history.') }); });
    return () => controller.abort();
  }, [userId, courtId, page, key]);
  return <section className="admin-detail-section">
    <h3>Retained change history</h3>
    {!current && <p role="status">Loading change history…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <>
      {current.data.total === 0 && <p>No administration changes have been recorded in this view.</p>}
      <ol className="admin-history">{current.data.events.map(event => {
        const { before, after } = event.details;
        return <li key={event.id}>
          <strong>{historyLabels[event.action] || event.action}</strong>
          <p>{parseServerDate(event.occurred_at).toISOString().replace('T', ' ').replace('Z', ' UTC')} · {event.details.actor_name || 'Database operator'}</p>
          {event.details.court_id && <p>{access.courts.find(court => court.id === event.details.court_id)?.name || `Court ${event.details.court_id}`}</p>}
          <p>{event.details.reason}</p>
          {Array.isArray(after) ? <p>Before: {Array.isArray(before) ? before.map(role => courtRoles[role] || role).join(', ') || 'No roles' : 'No roles'}.
            {' '}After: {after.map(role => courtRoles[role] || role).join(', ') || 'No roles'}.</p>
            : after && <dl className="admin-changes">{Object.entries(fieldLabels).filter(([field]) =>
              after[field] !== (before && !Array.isArray(before) ? before[field] : null),
            ).map(([field, label]) => <div key={field}><dt>{label}</dt><dd>
              {String(before && !Array.isArray(before) ? before[field] ?? 'Not set' : 'Not set')}
              {' → '}{String(after[field] ?? 'Not set')}
            </dd></div>)}</dl>}
        </li>;
      })}</ol>
      {current.data.total > 25 && <nav className="pagination" aria-label="Change history pages">
        <button className="btn btn-secondary btn-small" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous changes</button>
        <span>Page {page} of {Math.ceil(current.data.total / 25)}</span>
        <button className="btn btn-secondary btn-small" disabled={page * 25 >= current.data.total} onClick={() => setPage(n => n + 1)}>Next changes</button>
      </nav>}
    </>}
  </section>;
}

function AccountDirectory({ access }: { access: Access }) {
  const [court, setCourt] = useState(access.system_admin ? 0 : access.courts[0].id);
  const [email, setEmail] = useState('');
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Remote<Directory>>();
  const [editor, setEditor] = useState<Account | 'new' | null>(null);
  const [message, setMessage] = useState('');
  const editorRef = useRef<HTMLElement>(null);
  const selectedId = editor === 'new' ? 'new' : editor?.id;
  const key = `${court}:${email}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<Directory>('/admin/users', { params: { court_id: court || undefined, email: email || undefined, page }, signal: controller.signal })
      .then(response => { if (!controller.signal.aborted) setResult({ key, data: response.data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load accounts.') }); });
    return () => controller.abort();
  }, [court, email, page, key]);
  useEffect(() => { if (selectedId != null) editorRef.current?.focus(); }, [selectedId]);
  function saved(user: Account) {
    setMessage(editor !== 'new' && editor?.administration_version === user.administration_version
      ? 'No changes to record.' : 'Change recorded. Earlier values remain in the change history.');
    setEditor(user); setAttempt(n => n + 1);
  }
  return <>
    <div className="page-header"><div><h2>People &amp; court access</h2>
      <p>{access.system_admin ? 'Provision identities and delegate court access.' : 'Manage staff access for your assigned courts.'}</p></div>
      {access.system_admin && <button className="btn btn-primary" onClick={() => setEditor('new')}>Provision account</button>}</div>
    <form className="admin-directory-filter" onSubmit={event => {
      event.preventDefault(); setEmail(String(new FormData(event.currentTarget).get('email') || '').trim()); setPage(1); setEditor(null);
      setAttempt(n => n + 1); setMessage('');
    }}>
      <div className="form-group"><label htmlFor="directory-court">Directory scope</label>
        <select id="directory-court" value={court} onChange={event => { setCourt(Number(event.target.value)); setPage(1); setEditor(null); }}>
          {access.system_admin && <option value={0}>All accounts</option>}
          {access.courts.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></div>
      <div className="form-group"><label htmlFor="directory-email">Exact email address, optional</label>
        <input id="directory-email" name="email" type="email" maxLength={255} /></div>
      <button className="btn btn-secondary">Find accounts</button>
    </form>
    {court > 0 && <p><Link to={`/courts/${court}/intake`}>Manage this court&apos;s filing intake</Link></p>}
    {!access.system_admin && <p>Search the exact email of a known staff member to assign access. A system administrator must provision their identity first.</p>}
    {message && <p className="alert alert-success" role="status">{message}</p>}
    <div className="admin-workspace">
      <section aria-label="Account directory">
        {!current && <p role="status">Loading accounts…</p>}
        {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
        {current?.data && <>
          <p>{current.data.total} account{current.data.total === 1 ? '' : 's'}</p>
          {current.data.users.map(user => <article className="review-card admin-user-card" key={user.id}>
            <h3>{user.first_name} {user.last_name}</h3><p>{user.email}</p>
            <p>{accountTypes[user.user_type]} · {user.is_active ? 'Active' : 'Inactive'}</p>
            <button className="btn btn-secondary btn-small" onClick={() => setEditor(user)}>Manage {user.first_name} {user.last_name}</button>
          </article>)}
          {current.data.total > 25 && <nav className="pagination" aria-label="Account directory pages">
            <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous accounts</button>
            <span>Page {page} of {Math.ceil(current.data.total / 25)}</span>
            <button className="btn btn-secondary" disabled={page * 25 >= current.data.total} onClick={() => setPage(n => n + 1)}>Next accounts</button>
          </nav>}
        </>}
      </section>
      {editor && <section className="review-card admin-editor" ref={editorRef} tabIndex={-1}>
        <div className="history-summary"><h2>{editor === 'new' ? 'New account' : `${editor.first_name} ${editor.last_name}`}</h2>
          <button className="btn btn-secondary btn-small" onClick={() => { setEditor(null); setAttempt(n => n + 1); }}>Close &amp; refresh list</button></div>
        {access.system_admin && <AccountForm key={editor === 'new' ? 'new' : `${editor.id}:${editor.administration_version}`}
          user={editor === 'new' ? undefined : editor} self={editor !== 'new' && editor.id === access.user_id} onSaved={saved} />}
        {editor !== 'new' && <>
          <CourtAccess key={editor.id} user={editor} access={access} directoryCourt={court} onSaved={saved} />
          <AccountHistory key={`${editor.id}:${editor.administration_version}`} userId={editor.id} access={access} courtId={access.system_admin ? undefined : court} />
        </>}
      </section>}
    </div>
  </>;
}

export default function AdministrationPage() {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Remote<Access>>();
  const key = String(attempt);
  const current = result?.key === key ? result : undefined;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<Access>('/admin/access', { signal: controller.signal })
      .then(response => { if (!controller.signal.aborted) setResult({ key, data: response.data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not verify administrator access.') }); });
    return () => controller.abort();
  }, [key]);
  return <section className="administration-page">
    {!current && <p role="status">Checking administrator access…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.data && <AccountDirectory access={current.data} />}
  </section>;
}
