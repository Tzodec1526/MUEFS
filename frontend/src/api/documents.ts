import { apiClient } from './client';
import type { FilingEnvelope } from './filings';

export interface FilingFees {
  filing_id: number;
  version: number;
  source: 'court' | 'waiver' | 'service_only' | 'demo' | 'unassessed';
  assessment_id: string | null;
  authority_reference: string | null;
  items: Array<{ fee_type: string; amount_cents: number; description: string }>;
  total_cents: number | null;
  paid_cents: number;
  balance_due_cents: number | null;
  overpaid_cents: number;
  review_requested_at: string | null;
  review_reason: string | null;
  assessment_stale: boolean;
  can_request_review: boolean;
  can_assess: boolean;
  can_pay: boolean;
  can_request_waiver: boolean;
  obligation_met: boolean;
  payments_simulated: boolean;
}

export async function getFilingFees(filingId: number, signal?: AbortSignal): Promise<FilingFees & { filing: FilingEnvelope }> {
  const { data } = await apiClient.get(`/filings/${filingId}/fees`, { signal });
  return data;
}

export async function processPayment(
  envelopeId: number,
  amountCents: number,
  paymentMethod: string,
  feeVersion: number,
) {
  const { data } = await apiClient.post('/payments/process', {
    envelope_id: envelopeId,
    amount_cents: amountCents,
    payment_method: paymentMethod,
    expected_fee_version: feeVersion,
  });
  return data;
}
