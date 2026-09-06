import { useState, useEffect, lazy, Suspense, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { getFilingFees, processPayment, type FilingFees } from '../../api/documents';
import { updateFiling, uploadDocument, type FilingEnvelope } from '../../api/filings';
import { formatCents, parseServerDate } from '../../utils/format';
import { getErrorDetail } from '../../utils/errors';
import LoadError from '../common/LoadError';

const FeeAssessmentForm = lazy(() => import('../clerk/FeeAssessmentForm'));

export default function PaymentForm({ filingId, onFeesChange }: {
  filingId: number; onFeesChange?: (filing: FilingEnvelope, obligationMet: boolean) => void;
}) {
  const [result, setResult] = useState<{ key: string; fees?: FilingFees; filing?: FilingEnvelope; error?: string }>();
  const [attempt, setAttempt] = useState(0);
  const [paymentMethod, setPaymentMethod] = useState('credit_card');
  const [waiverFile, setWaiverFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const key = `${filingId}:${attempt}`;
  const current = result?.key === key ? result : undefined;
  const fees = current?.fees, filing = current?.filing;
  const selectedMethod = fees?.can_pay ? paymentMethod : 'waiver';
  useEffect(() => {
    const controller = new AbortController();
    getFilingFees(filingId, controller.signal)
      .then(fees => {
        if (controller.signal.aborted) return;
        const filing = fees.filing;
        setResult({ key, fees, filing });
        onFeesChange?.(filing, fees.obligation_met);
      })
      .catch(err => { if (!controller.signal.aborted) setResult({ key, error: getErrorDetail(err) || 'Could not load filing fees.' }); });
    return () => controller.abort();
  }, [filingId, key, onFeesChange]);

  async function requestReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!fees) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(''); setNotice('');
    try {
      await apiClient.post(`/filings/${filingId}/fee-review`, { expected_version: fees.version, reason: form.get('reason') });
      setNotice('Fee review requested. The court can now review the documents and amount due.');
      setAttempt(n => n + 1);
    } catch (err) { setError(getErrorDetail(err) || 'Could not request fee review.'); }
    finally { setBusy(false); }
  }

  async function pay() {
    if (!fees || !filing) return;
    setBusy(true); setError(''); setNotice('');
    try {
      if (selectedMethod === 'waiver') {
        if (!filing.documents.some(doc => doc.document_type_code === 'FEE_WAIVER')) {
          if (!waiverFile) { setError('Attach the completed, signed Fee Waiver Request (MC 20).'); return; }
          await uploadDocument(filingId, waiverFile, 'FEE_WAIVER', 'Fee Waiver Request (MC 20)', true);
        }
        await updateFiling(filingId, { fee_waiver_requested: true });
        setNotice('Fee waiver request attached. Submit the filing to send the application for court review.');
      } else {
        if (fees.balance_due_cents === null) return;
        await processPayment(filingId, fees.balance_due_cents, selectedMethod, fees.version);
        setNotice('Simulated payment recorded. No money was charged.');
      }
      setAttempt(n => n + 1);
    } catch (err) { setError(getErrorDetail(err) || 'Could not record payment or the fee waiver request. Refresh before retrying.'); }
    finally { setBusy(false); }
  }

  if (!current) return <p role="status">Loading filing fees…</p>;
  if (current.error) return <LoadError message={current.error} onRetry={() => setAttempt(n => n + 1)} />;
  if (!fees || !filing) return null;
  const canChoosePayment = !fees.obligation_met && (fees.can_pay || fees.can_request_waiver);
  return <div className="review-card filing-fees">
    <div className="page-header"><h3>Filing fees &amp; payments</h3>
      <button className="btn btn-secondary btn-small" disabled={busy} onClick={() => { setError(''); setAttempt(n => n + 1); }}>Refresh fees</button></div>
    {notice && <p className="alert alert-success" role="status">{notice}</p>}
    {error && <p className="alert alert-error" role="alert">{error}</p>}
    {fees.source === 'demo' && <p className="alert alert-info">This is a synthetic example amount for the demo. It is not a court-approved fee quote.</p>}
    {fees.assessment_stale && <p className="alert alert-warning">The documents or fee-review request changed after the last assessment. A current court assessment is required.</p>}
    {fees.source === 'court' && <p>Court assessment #{fees.assessment_id} · {fees.authority_reference}</p>}
    {fees.source === 'waiver' && <p>The fee waiver decision controls the amount due. Read the signed decision in filing history.</p>}
    {fees.review_requested_at && <p className="alert alert-info" role="status">Awaiting court fee review, requested {parseServerDate(fees.review_requested_at).toISOString().replace('T', ' ').replace('Z', ' UTC')}.</p>}
    {fees.total_cents === null ? <p>A fee has not been established for the current documents.</p>
      : <div className="fee-summary">
        {fees.items.map((item, index) => <div className="fee-item" key={index}><span>{item.description}</span><span>{formatCents(item.amount_cents)}</span></div>)}
        <div className="fee-item"><strong>Assessed total</strong><strong>{formatCents(fees.total_cents)}</strong></div>
        <div className="fee-item"><span>Completed payments</span><span>{formatCents(fees.paid_cents)}</span></div>
        <div className="fee-total"><strong>Balance due</strong><strong>{formatCents(fees.balance_due_cents ?? 0)}</strong></div>
      </div>}
    {fees.overpaid_cents > 0 && <p className="alert alert-warning">Recorded payments exceed the assessment by {formatCents(fees.overpaid_cents)}. Court reconciliation is required; a refund has not been issued.</p>}
    {fees.obligation_met && <p className="alert alert-success">{filing.fee_waiver_requested && filing.fee_waiver_granted === null
      ? 'The pending fee waiver application allows submission for court review.' : 'No additional payment is required for the current filing.'}</p>}
    <p className="info-text">Fee review does not submit a draft or establish its filing date. <Link to={`/filings/${filingId}/history`}>View receipts and decisions</Link>.</p>
    {fees.can_request_review && <form onSubmit={requestReview} className="fee-review-request">
      <div className="form-group"><label htmlFor="fee-review-reason">Reason for court fee review</label>
        <textarea id="fee-review-reason" name="reason" required maxLength={2000} rows={2} disabled={busy} /></div>
      <button type="submit" className="btn btn-secondary" disabled={busy}>Request court fee review</button>
    </form>}
    {canChoosePayment && <>
      <div className="payment-methods"><h4>Payment or waiver</h4><div className="payment-option-list">
        {[
          { value: 'credit_card', label: 'Credit card' }, { value: 'debit_card', label: 'Debit card' },
          { value: 'ach', label: 'ACH / eCheck' }, { value: 'waiver', label: 'Fee waiver request' },
        ].filter(method => method.value === 'waiver' ? fees.can_request_waiver : fees.can_pay).map(method => <label
          key={method.value} className={`payment-option ${selectedMethod === method.value ? 'selected' : ''}`}>
          <input type="radio" name="paymentMethod" value={method.value} checked={selectedMethod === method.value}
            disabled={busy || (method.value !== 'waiver' && !fees.payments_simulated)} onChange={() => setPaymentMethod(method.value)} />{method.label}
        </label>)}
      </div></div>
      {selectedMethod === 'waiver' && fees.can_request_waiver && <div className="fee-waiver-section">
        <p>Complete and sign the <a href="https://www.courts.michigan.gov/siteassets/forms/scao-approved/mc20.pdf" target="_blank" rel="noreferrer">approved Fee Waiver Request (MC 20)</a>. The application accompanies your filing and remains nonpublic.</p>
        {filing.documents.some(doc => doc.document_type_code === 'FEE_WAIVER') ? <p>A fee waiver application is already attached. Review it with your documents.</p>
          : <div className="form-group"><label htmlFor="waiver-application">Completed, signed application (PDF)</label>
            <input id="waiver-application" type="file" accept="application/pdf,.pdf" disabled={busy} onChange={event => setWaiverFile(event.target.files?.[0] || null)} /></div>}
        <p>If filing as a prisoner under the Michigan Department of Corrections, also attach the certified institutional account statement required by MCR 2.002(B), marked confidential.</p>
      </div>}
      {fees.can_pay && <p className="info-text">{fees.payments_simulated ? 'Payment records are simulated. No card or bank information is collected and no money is charged.' : 'Online payment is unavailable. Contact the court about payment options.'}</p>}
      <button className="btn btn-primary" disabled={busy || (selectedMethod === 'waiver' ? !fees.can_request_waiver : !fees.can_pay || !fees.payments_simulated)} onClick={pay}>
        {busy ? 'Recording…' : selectedMethod === 'waiver' ? 'Attach waiver request to filing' : `Record simulated payment — ${formatCents(fees.balance_due_cents ?? 0)}`}
      </button>
    </>}
    {fees.can_assess && <Suspense fallback={<p role="status">Loading assessment form…</p>}>
      <FeeAssessmentForm key={key} fees={fees} filing={filing} onSaved={() => { setNotice('Court fee assessment recorded.'); setAttempt(n => n + 1); }} />
    </Suspense>}
  </div>;
}
