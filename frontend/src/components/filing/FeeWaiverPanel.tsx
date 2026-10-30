import { useState, type FormEvent } from 'react';
import { decideFeeWaiver, type FeeWaiverState } from '../../api/filings';
import { processPayment } from '../../api/documents';
import { formatCents } from '../../utils/format';
import { errorMessage } from '../../utils/errors';

export const waiverActionLabels: Record<string, string> = {
  grant_public_assistance: 'Clerk waiver: means-tested public assistance',
  grant_legal_services: 'Clerk waiver: qualifying legal services representation',
  refer: 'Refer for judicial review',
  grant_judicial: 'Judicial order: grant waiver',
  deny_judicial: 'Judicial order: deny waiver',
};

export default function FeeWaiverPanel({ filingId, waiver, onChange }: {
  filingId: number; waiver: FeeWaiverState; onChange: () => void;
}) {
  const [action, setAction] = useState(waiver.allowed_actions[0] || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const state = waiver.granted === true ? 'Granted' : waiver.granted === false ? 'Denied'
    : waiver.referred_at ? 'Awaiting judicial review' : 'Awaiting court review';

  async function recordDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const dollars = form.get('amount_dollars');
    form.delete('amount_dollars');
    if (action === 'deny_judicial') form.set('amount_due_cents', String(Math.round(Number(dollars) * 100)));
    form.set('expected_fee_version', String(waiver.fee_version));
    setBusy(true);
    setError(null);
    try {
      await decideFeeWaiver(filingId, form);
      onChange();
    } catch (err) {
      setError(errorMessage(err, 'Could not record the fee waiver decision. Refresh history before retrying.'));
    } finally { setBusy(false); }
  }

  async function pay() {
    if (waiver.balance_due_cents == null) return;
    setBusy(true);
    setError(null);
    try {
      await processPayment(filingId, waiver.balance_due_cents, 'credit_card', waiver.fee_version);
      onChange();
    } catch (err) {
      setError(errorMessage(err, 'Could not record payment. Refresh history before retrying.'));
    } finally { setBusy(false); }
  }

  return <div className="review-card fee-waiver-panel">
    <h2 className="card-heading">Fee waiver: {state}</h2>
    <p>The application and signed decision are nonpublic. Filing acceptance is a separate decision.</p>
    {waiver.granted !== null && !waiver.decided_at && <p className="alert alert-warning">
      This is an older waiver record. A separate signed decision was not recorded in this system.
    </p>}
    {waiver.amount_due_cents != null && <p>
      Amount in the decision: <strong>{formatCents(waiver.amount_due_cents)}</strong>
      {waiver.balance_due_cents != null && <> · Remaining balance: <strong>{formatCents(waiver.balance_due_cents)}</strong></>}
    </p>}
    {waiver.granted === false && <p>
      Read the signed order and court notice for payment and review deadlines. Contact the court
      to request review of a denial. Recording payment here does not determine the legal filing date.
    </p>}
    {waiver.can_pay && <div className="waiver-payment">
      {waiver.payments_simulated ? <>
        <p>Demo payment: no card information is collected and no money is charged.</p>
        <button className="btn btn-primary" disabled={busy} onClick={pay}>
          {busy ? 'Processing…' : `Record simulated payment of ${formatCents(waiver.balance_due_cents!)}`}
        </button>
      </> : <p>Online payment is unavailable. Contact the court about payment options.</p>}
    </div>}
    {waiver.allowed_actions.length > 0 && <form onSubmit={recordDecision}>
      <div className="form-group">
        <label htmlFor="waiver-action">Waiver action</label>
        <select id="waiver-action" name="action" value={action} disabled={busy}
          onChange={e => setAction(e.target.value)}>
          {waiver.allowed_actions.map(value => <option key={value} value={value}>{waiverActionLabels[value]}</option>)}
        </select>
      </div>
      {action !== 'refer' && <div className="form-group">
        <label htmlFor="waiver-order">Signed waiver or judicial order (PDF)</label>
        <input id="waiver-order" name="file" type="file" accept="application/pdf,.pdf" required disabled={busy} />
        <p className="info-text">Attach the completed, signed decision on the approved form. It will remain in private history.</p>
      </div>}
      <div className="form-group">
        <label htmlFor="waiver-decision-reason">{action === 'deny_judicial' ? 'Reason in the denial order' : 'Court note (optional)'}</label>
        <textarea id="waiver-decision-reason" name="reason" rows={3} maxLength={5000}
          required={action === 'deny_judicial'} disabled={busy} />
      </div>
      {action === 'deny_judicial' && <div className="form-group">
        <label htmlFor="waiver-amount">Amount due under the order (USD)</label>
        <input id="waiver-amount" name="amount_dollars" type="number" min="0" max="1000000" step="0.01" required disabled={busy} />
      </div>}
      <p className="info-text">Court staff must send the signed decision and required notice through an authorized
        channel. An in-app record does not establish delivery or calculate deadlines.</p>
      <button className="btn btn-primary" disabled={busy}>{busy ? 'Recording…' : action === 'refer' ? 'Refer for judicial review' : 'Record signed decision'}</button>
    </form>}
    {error && <div className="alert alert-error" role="alert">
      <p>{error}</p><button className="btn btn-secondary" onClick={onChange}>Refresh history</button>
    </div>}
  </div>;
}
