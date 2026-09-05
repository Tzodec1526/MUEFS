import { useState, useEffect } from 'react';
import { calculateFees, processPayment, type FilingFees } from '../../api/documents';
import { updateFiling } from '../../api/filings';
import { formatCents as formatCurrency } from '../../utils/format';
import { getErrorDetail } from '../../utils/errors';
import LoadError from '../common/LoadError';

interface Props {
  courtId: number;
  caseTypeId: number;
  filingId: number;
  onPaymentComplete: () => void;
  filingType?: string;
}

function PaymentForm({ courtId, caseTypeId, filingId, onPaymentComplete, filingType = 'initial' }: Props) {
  const [fees, setFees] = useState<FilingFees | null>(null);
  const [loading, setLoading] = useState(true);
  const [feeError, setFeeError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [paymentMethod, setPaymentMethod] = useState('credit_card');
  const [waiverReason, setWaiverReason] = useState('');

  useEffect(() => {
    let active = true;
    async function fetchFees() {
      setLoading(true);
      setFeeError(null);
      try {
        const result = await calculateFees(courtId, caseTypeId, filingType);
        if (!active) return;
        setFees(result);
        if (result.total_cents === 0) {
          onPaymentComplete();
        }
      } catch (err) {
        if (active) setFeeError(getErrorDetail(err) || 'Could not calculate filing fees.');
      } finally {
        if (active) setLoading(false);
      }
    }
    fetchFees();
    return () => { active = false; };
  }, [courtId, caseTypeId, filingType, onPaymentComplete, attempt]);

  const [processing, setProcessing] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  const handlePay = async () => {
    if (!fees) return;

    // Fee waiver — persist the request + reason to the envelope, then advance. The
    // submit endpoint allows fee-waiver filings without payment.
    if (paymentMethod === 'waiver' && !waiverReason.trim()) {
      setPayError('Please describe why you are unable to pay the filing fee.');
      return;
    }
    setProcessing(true);
    setPayError(null);
    try {
      if (paymentMethod === 'waiver') {
        await updateFiling(filingId, {
          fee_waiver_requested: true,
          fee_waiver_reason: waiverReason.trim(),
        });
      } else {
        await processPayment(filingId, fees.total_cents, paymentMethod);
      }
      onPaymentComplete();
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
              ].map((method) => (
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
                  Under MCR 2.002, you may request a fee waiver if you are unable to pay filing fees.
                  You must demonstrate financial hardship. The court will review your request and
                  may grant a full or partial waiver.
                </p>
              </div>
              <div className="form-group">
                <label htmlFor="waiverReason">Reason for Fee Waiver Request <span className="required-marker">*</span></label>
                <textarea
                  id="waiverReason"
                  rows={3}
                  value={waiverReason}
                  placeholder="Describe why you are unable to pay the filing fee (e.g., receiving public assistance, income below poverty guidelines, financial hardship)..."
                  onChange={(e) => setWaiverReason(e.target.value)}
                />
              </div>
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
                ? 'Submit Fee Waiver Request'
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
