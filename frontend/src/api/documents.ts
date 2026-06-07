import { apiClient } from './client';

export async function calculateFees(
  courtId: number,
  caseTypeId: number,
  documentCount: number = 1,
  filingType: string = 'initial',
) {
  const { data } = await apiClient.post('/payments/calculate', {
    court_id: courtId,
    case_type_id: caseTypeId,
    document_count: documentCount,
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
