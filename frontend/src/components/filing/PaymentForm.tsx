import { useState, useEffect } from 'react';
import { calculateFees } from '../../api/documents';

interface Props {
  courtId: number;
  caseTypeId: number;
  onPaymentComplete: (paymentId: number) => void;
}

function PaymentForm({ courtId, caseTypeId, onPaymentComplete }: Props) {
  const [fees, setFees] = useState<{
    filing_fee_cents: number;
    total_cents: number;
    fee_description: string;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchFees() {
      try {
        const result = await calculateFees(courtId, caseTypeId);
        setFees(result);
      } catch {
        setFees(null);
      } finally {
        setLoading(false);
      }
    }
    fetchFees();
  }, [courtId, caseTypeId]);

  const formatCurrency = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  if (loading) return <p>Calculating fees...</p>;

  return (
    <div className="form-section">
      <h3>Filing Fees</h3>

      {fees && (
        <div className="fee-summary">
          <div className="fee-item">
            <span>{fees.fee_description}</span>
            <span>{formatCurrency(fees.filing_fee_cents)}</span>
          </div>
          <div className="fee-total">
            <strong>Total Due</strong>
            <strong>{formatCurrency(fees.total_cents)}</strong>
          </div>
        </div>
      )}

      <div className="payment-methods">
        <h4>Payment Method</h4>
        <p className="info-text">
          Payment processing integration coming in Phase 2.
          For the MVP, fees are recorded but not charged.
        </p>
        <button
          className="btn btn-primary"
          onClick={() => onPaymentComplete(0)}
        >
          Continue (Fee Waived for Demo)
        </button>
      </div>
    </div>
  );
}

export default PaymentForm;
