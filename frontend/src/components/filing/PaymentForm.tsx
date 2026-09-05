import { useState, useEffect } from 'react';
import { calculateFees, processPayment, type FilingFees } from '../../api/documents';
import { getFiling, updateFiling, uploadDocument, type FilingEnvelope } from '../../api/filings';
import { formatCents as formatCurrency } from '../../utils/format';
import { getErrorDetail } from '../../utils/errors';
import LoadError from '../common/LoadError';

interface Props {
  courtId: number;
  caseTypeId: number;
  filingId: number;
  onPaymentComplete: (filing: FilingEnvelope) => void;
  filingType?: string;
}

function PaymentForm({ courtId, caseTypeId, filingId, onPaymentComplete, filingType = 'initial' }: Props) {
  const [fees, setFees] = useState<FilingFees | null>(null);
  const [loading, setLoading] = useState(true);
  const [feeError, setFeeError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [paymentMethod, setPaymentMethod] = useState('credit_card');
  const [waiverFile, setWaiverFile] = useState<File | null>(null);
  const [currentFiling, setCurrentFiling] = useState<FilingEnvelope | null>(null);

  useEffect(() => {
    let active = true;
    async function fetchFees() {
      setLoading(true);
      setFeeError(null);
      try {
        const [result, filing] = await Promise.all([
          calculateFees(courtId, caseTypeId, filingType), getFiling(filingId),
        ]);
        if (!active) return;
        setCurrentFiling(filing);
        setFees(filing.fee_waiver_amount_due_cents != null ? {
          ...result, filing_fee_cents: filing.fee_waiver_amount_due_cents,
          total_cents: filing.fee_waiver_amount_due_cents, additional_fees: [],
          fee_description: 'Amount under the fee waiver decision',
        } : result);
        if (filing.payment_id != null || filing.fee_waiver_granted === true
            || (filing.fee_waiver_amount_due_cents ?? result.total_cents) === 0) {
          onPaymentComplete(filing);
        }
      } catch (err) {
        if (active) setFeeError(getErrorDetail(err) || 'Could not calculate filing fees.');
      } finally {
        if (active) setLoading(false);
      }
    }
    fetchFees();
    return () => { active = false; };
  }, [courtId, caseTypeId, filingId, filingType, onPaymentComplete, attempt]);

  const [processing, setProcessing] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  const handlePay = async () => {
    if (!fees) return;

    setProcessing(true);
    setPayError(null);
    try {
      const filing = await getFiling(filingId);
      if (filing.payment_id != null || filing.fee_waiver_granted === true) {
        onPaymentComplete(filing);
        return;
      }
      if (paymentMethod === 'waiver') {
        if (!filing.documents.some(doc => doc.document_type_code === 'FEE_WAIVER')) {
          if (!waiverFile) {
            setPayError('Attach the completed, signed Fee Waiver Request (MC 20).');
            return;
          }
          await uploadDocument(filingId, waiverFile, 'FEE_WAIVER', 'Fee Waiver Request (MC 20)', true);
        }
        onPaymentComplete(await updateFiling(filingId, { fee_waiver_requested: true }));
      } else {
        await processPayment(filingId, fees.total_cents, paymentMethod);
        onPaymentComplete(await getFiling(filingId));
      }
    } catch (err: unknown) {
      setPayError(getErrorDetail(err) || 'Could not record payment or fee waiver.');
    } finally {
      setProcessing(false);
    }
  };

  if (loading) {
    return (
      <div className="review-card">
        <h4>Filing Fees</h4>
        <p>Calculating fees...</p>
      </div>
    );
  }

  if (feeError) return <LoadError message={feeError} onRetry={() => setAttempt(n => n + 1)} />;

  const showSimulated = fees?.is_simulated;

  return (
    <div className="review-card">
      <h4>Filing Fees</h4>
      {showSimulated && (
        <div className="alert alert-info" role="status">
          <strong>Simulated payment</strong>
          <p>
            {fees?.simulation_notice ||
              'No card or bank data is sent. This demo records fees for workflow testing only.'}
          </p>
        </div>
      )}
      <p className="info-text">
        Review the fees below and select a payment method to continue.
      </p>

      {fees && (
        <>
          <div className="fee-summary">
            <div className="fee-item">
              <span>{fees.fee_description}</span>
              <span>{formatCurrency(fees.filing_fee_cents)}</span>
            </div>
            {fees.additional_fees.map((af, i) => (
              <div key={i} className="fee-item">
                <span>{af.description}</span>
                <span>{formatCurrency(af.amount_cents)}</span>
              </div>
            ))}
            <div className="fee-total">
              <strong>Total Due</strong>
              <strong>{formatCurrency(fees.total_cents)}</strong>
            </div>
          </div>

          <div className="payment-methods">
            <h4>Payment Method</h4>
            <div className="payment-option-list">
              {[
                { value: 'credit_card', label: 'Credit Card', desc: 'Visa, MasterCard, Discover, AMEX' },
                { value: 'debit_card', label: 'Debit Card', desc: 'With Visa/MasterCard logo' },
                { value: 'ach', label: 'ACH / eCheck', desc: 'Direct bank transfer' },
                { value: 'waiver', label: 'Fee Waiver', desc: 'Request fee waiver (must qualify)' },
              ].filter(method => method.value !== 'waiver' || currentFiling?.fee_waiver_granted == null).map((method) => (
                <label
                  key={method.value}
                  className={`payment-option ${paymentMethod === method.value ? 'selected' : ''}`}
                >
                  <input
                    type="radio"
                    name="paymentMethod"
                    value={method.value}
                    checked={paymentMethod === method.value}
                    disabled={method.value !== 'waiver' && !showSimulated}
                    onChange={(e) => setPaymentMethod(e.target.value)}
                  />
                  <div>
                    <strong>{method.label}</strong>
                    <span>{method.desc}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {paymentMethod === 'waiver' && (
            <div className="fee-waiver-section">
              <div className="alert alert-info">
                <strong>Fee Waiver Request (MCR 2.002)</strong>
                <p>
                  Complete and sign the <a href="https://www.courts.michigan.gov/siteassets/forms/scao-approved/mc20.pdf" target="_blank" rel="noreferrer">approved Fee Waiver Request (MC 20)</a>.
                  The application accompanies your filing and remains nonpublic.
                </p>
              </div>
              {currentFiling?.documents.some(doc => doc.document_type_code === 'FEE_WAIVER')
                ? <p>A fee waiver application is already attached. Review it in the Documents step.</p>
                : <div className="form-group">
                  <label htmlFor="waiver-application">Completed, signed application (PDF)</label>
                  <input id="waiver-application" type="file" accept="application/pdf,.pdf"
                    onChange={e => setWaiverFile(e.target.files?.[0] || null)} />
                </div>}
              <p>If filing as a prisoner under the Michigan Department of Corrections, also attach the certified
                institutional account statement required by MCR 2.002(B), marked confidential.</p>
            </div>
          )}

          <div className="payment-note">
            <p className="info-text">
              {paymentMethod === 'waiver'
                ? 'Your fee waiver request will be reviewed by the court. If denied, you will be notified and may pay the fee at that time.'
                : showSimulated
                  ? 'Confirming below records a simulated payment. No money is charged.'
                  : 'Online payment is currently unavailable. Contact the court about payment options.'}
            </p>
          </div>

          {payError && (
            <div className="alert alert-error" role="alert">{payError}</div>
          )}

          <button className="btn btn-primary btn-large" onClick={handlePay} disabled={processing || (paymentMethod !== 'waiver' && !showSimulated)}>
            {processing
              ? 'Processing...'
              : paymentMethod === 'waiver'
                ? 'Attach waiver request to filing'
                : showSimulated
                  ? `Confirm (simulated) \u2014 ${formatCurrency(fees.total_cents)}`
                  : `Confirm Payment \u2014 ${formatCurrency(fees.total_cents)}`}
          </button>
        </>
      )}
    </div>
  );
}

export default PaymentForm;
