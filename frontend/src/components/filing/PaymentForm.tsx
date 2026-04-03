import { useState, useEffect } from 'react';
import { calculateFees } from '../../api/documents';

interface Props {
  courtId: number;
  caseTypeId: number;
  onPaymentComplete: () => void;
}

function PaymentForm({ courtId, caseTypeId, onPaymentComplete }: Props) {
  const [fees, setFees] = useState<{
    filing_fee_cents: number;
    total_cents: number;
    fee_description: string;
    additional_fees: Array<{ fee_type: string; amount_cents: number; description: string }>;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [paymentMethod, setPaymentMethod] = useState('credit_card');
  const [completed, setCompleted] = useState(false);

  useEffect(() => {
    async function fetchFees() {
      try {
        const result = await calculateFees(courtId, caseTypeId);
        setFees(result);
        // If no fee, auto-complete
        if (result.total_cents === 0) {
          setCompleted(true);
          onPaymentComplete();
        }
      } catch {
        setFees(null);
      } finally {
        setLoading(false);
      }
    }
    fetchFees();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onPaymentComplete is stable from parent
  }, [courtId, caseTypeId]);

  const formatCurrency = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  const handlePay = () => {
    setCompleted(true);
    onPaymentComplete();
  };

  if (loading) {
    return (
      <div className="form-section">
        <h3>Filing Fees</h3>
        <p>Calculating fees...</p>
      </div>
    );
  }

  if (completed) {
    return (
      <div className="form-section">
        <h3>Filing Fees</h3>
        <div className="payment-confirmed">
          <span className="payment-check">&#10003;</span>
          <p>
            {fees && fees.total_cents > 0
              ? `Payment of ${formatCurrency(fees.total_cents)} confirmed.`
              : 'No filing fee required for this case type.'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="form-section">
      <h3>Filing Fees</h3>
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

          <div className="payment-note">
            <p className="info-text">
              Payment processing integration coming in Phase 2. For the MVP demo,
              clicking "Confirm Payment" will record the fee without charging.
            </p>
          </div>

          <button className="btn btn-primary btn-large" onClick={handlePay}>
            Confirm Payment &mdash; {formatCurrency(fees.total_cents)}
          </button>
        </>
      )}
    </div>
  );
}

export default PaymentForm;
