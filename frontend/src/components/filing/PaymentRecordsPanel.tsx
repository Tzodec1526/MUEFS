import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import type { FilingFees } from '../../api/documents';
import type { PaymentRecord, PaymentRecords } from '../../api/payments';
import { formatCents, parseServerDate } from '../../utils/format';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import LoadError from '../common/LoadError';

type PendingRequest = { path: string; body: Record<string, unknown>; key?: string };

export default function PaymentRecordsPanel({ fees, onChanged, onBusyChange }: {
  fees: FilingFees; onChanged: (message: string) => void; onBusyChange: (busy: boolean) => void;
}) {
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; records?: PaymentRecords; error?: LoadFailure }>();
  const [editing, setEditing] = useState<'new' | PaymentRecord | null>(null);
  const [pending, setPending] = useState<PendingRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const base = `/filings/${fees.filing_id}`;
  const key = `${fees.filing_id}:${fees.payment_version}:${page}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  const stale = current?.records != null && current.records.payment_version !== fees.payment_version;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get<PaymentRecords>(`${base}/payments`, { params: { page }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResult({ key, records: data }); })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: loadFailure(err, 'Could not load payment records.') }); });
    return () => controller.abort();
  }, [base, key, page]);

  async function send(operation: PendingRequest) {
    setBusy(true); setPending(operation); onBusyChange(true); setError('');
    try {
      const { data } = await apiClient.post<PaymentRecord>(operation.path, operation.body,
        { headers: operation.key ? { 'Idempotency-Key': operation.key } : undefined });
      setPending(null); setEditing(null); onBusyChange(false);
      onChanged(data.status === 'reversed'
        ? 'The external payment credit is reversed. Review the updated balance. No refund was issued by this portal.'
        : 'External receipt credited to this filing. The source and verification are retained in filing history.');
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status && status >= 400 && status < 500) {
        setPending(null); onBusyChange(false);
        setError(errorMessage(err, 'The request was rejected. Review the current fee and payment records.'));
      } else {
        setError('The outcome is unknown. Retry the same request to confirm whether the credit or reversal was recorded.');
      }
    } finally { setBusy(false); }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (stale) return;
    const form = new FormData(event.currentTarget);
    if (editing === 'new') {
      void send({ path: `${base}/external-payments`, key: crypto.randomUUID(), body: {
        expected_fee_version: fees.version, expected_payment_version: fees.payment_version,
        amount_cents: Math.round(Number(form.get('amount')) * 100),
        receipt_system: form.get('receipt_system'), receipt_reference: form.get('receipt_reference'),
        received_at: new Date(String(form.get('received_at'))).toISOString(),
        reason: form.get('reason'), verified: true,
      } });
    } else if (editing) {
      void send({ path: `${base}/external-payments/${editing.id}/reverse`, body: {
        expected_payment_version: fees.payment_version, reason: form.get('reason'), reviewed: true,
      } });
    }
  }

  return <section className="payment-records" aria-label="Payment records">
    <div className="page-header"><h4>Payment records for filing #{fees.filing_id}</h4>
      {fees.can_record_external_payment && current?.records && !stale && !editing && <button className="btn btn-secondary" onClick={() => {
        setEditing('new'); setError('');
      }}>Record external receipt</button>}</div>
    {error && <p className="alert alert-error" role="alert">{error}</p>}
    {stale && <p className="alert alert-warning" role="alert">Payment records changed. Refresh fees and review the balance before recording another change.</p>}
    {pending && !busy && <button className="btn btn-primary" onClick={() => void send(pending)}>Retry same request</button>}
    {editing && <form onSubmit={submit} className="external-payment-form">
      <fieldset disabled={pending !== null}>
        <legend>{editing === 'new' ? 'Record a verified external receipt' : `Reverse credit of ${formatCents(editing.amount_cents)}`}</legend>
        {editing === 'new' ? <>
          <p>Use a receipt already verified in the court’s payment records and allocated only to this filing. This portal records the credit; it does not collect funds.</p>
          <div className="calendar-range">
            <div className="form-group"><label htmlFor="external-receipt-system">Receipt system or court cashier</label>
              <input id="external-receipt-system" name="receipt_system" required maxLength={120} /></div>
            <div className="form-group"><label htmlFor="external-receipt-reference">External receipt number</label>
              <input id="external-receipt-reference" name="receipt_reference" required maxLength={200} /></div>
          </div>
          <div className="calendar-range">
            <div className="form-group"><label htmlFor="external-receipt-amount">Amount credited (USD)</label>
              <input id="external-receipt-amount" name="amount" type="number" min="0.01" step="0.01"
                max={(fees.balance_due_cents ?? 0) / 100} defaultValue={((fees.balance_due_cents ?? 0) / 100).toFixed(2)} required /></div>
            <div className="form-group"><label htmlFor="external-receipt-time">Received by the external system</label>
              <input id="external-receipt-time" name="received_at" type="datetime-local" required aria-describedby="external-receipt-zone" />
              <p id="external-receipt-zone">Enter the time in your device’s time zone: {Intl.DateTimeFormat().resolvedOptions().timeZone}.</p></div>
          </div>
        </> : <p>This removes the {formatCents(editing.amount_cents)} credit from this filing’s balance. The original entry stays in history. Correct the external accounting records separately; this action does not issue a refund or change a received filing’s status.</p>}
        <div className="form-group"><label htmlFor="external-payment-reason">{editing === 'new' ? 'Verification reason and source' : 'Reason for reversing this credit'}</label>
          <textarea id="external-payment-reason" name="reason" required maxLength={2000} rows={3} /></div>
        <label className="checkbox-label"><input type="checkbox" required />
          {editing === 'new' ? 'I verified the source receipt, amount and allocation to this filing.' : 'I reviewed the source records and the effect on this filing’s balance.'}</label>
        <div className="button-row">
          <button className="btn btn-primary" type="submit" disabled={stale}>{busy ? 'Recording…' : editing === 'new' ? 'Record receipt credit' : 'Reverse this credit'}</button>
          <button className="btn btn-secondary" type="button" onClick={() => { setEditing(null); setError(''); }}>Cancel</button>
        </div>
      </fieldset>
    </form>}
    {!current && <p role="status">Loading payment records…</p>}
    {current?.error && <LoadError failure={current.error} onRetry={() => setAttempt(n => n + 1)} />}
    {current?.records && <>
      <p>{current.records.total} payment records</p>
      {current.records.total === 0 && <p>No payments have been recorded for this filing.</p>}
      <ol className="payment-record-list">{current.records.payments.map(payment => <li key={payment.id}>
        <div className="page-header"><strong>{formatCents(payment.amount_cents)}</strong>
          <span>{payment.status === 'reversed' ? 'Credit reversed' : payment.status === 'completed' ? 'Completed' : payment.status}{payment.is_simulated && ' · Simulated'}</span></div>
        {payment.external_receipt ? <>
          <p>{payment.external_receipt.system} · Receipt {payment.external_receipt.reference}</p>
          <p>Received {parseServerDate(payment.external_receipt.received_at).toLocaleString()} · Recorded by {payment.external_receipt.recorded_by_name}</p>
          <details><summary>Verification</summary><p>{payment.external_receipt.reason}</p></details>
        </> : <p>{payment.transaction_ref || 'No transaction reference retained'}</p>}
        {fees.can_manage_external_payments && !stale && payment.external_receipt && payment.status === 'completed' && !editing &&
          <button className="btn btn-secondary btn-small" onClick={() => { setEditing(payment); setError(''); }}>Reverse credit</button>}
      </li>)}</ol>
      {current.records.total > 25 && <nav className="pagination" aria-label="Payment record pages">
        <button className="btn btn-secondary" disabled={page === 1 || pending !== null} onClick={() => setPage(n => n - 1)}>Previous</button>
        <span>Page {page} of {Math.ceil(current.records.total / 25)}</span>
        <button className="btn btn-secondary" disabled={page * 25 >= current.records.total || pending !== null} onClick={() => setPage(n => n + 1)}>Next</button>
      </nav>}
    </>}
    <p><Link to={`/filings/${fees.filing_id}/history`}>View retained payment changes and filing receipts</Link></p>
  </section>;
}
