import { apiClient } from './client';

export interface FilingFees {
  filing_fee_cents: number;
  total_cents: number;
  fee_description: string;
  additional_fees: Array<{ fee_type: string; amount_cents: number; description: string }>;
  is_simulated: boolean;
  simulation_notice: string;
}

export async function calculateFees(
  courtId: number,
  caseTypeId: number,
  filingType: string = 'initial',
): Promise<FilingFees> {
  const { data } = await apiClient.post('/payments/calculate', {
    court_id: courtId,
    case_type_id: caseTypeId,
    filing_type: filingType,
  });
  return data;
}

export async function processPayment(
  envelopeId: number,
  amountCents: number,
  paymentMethod: string,
) {
  const { data } = await apiClient.post('/payments/process', {
    envelope_id: envelopeId,
    amount_cents: amountCents,
    payment_method: paymentMethod,
  });
  return data;
}
