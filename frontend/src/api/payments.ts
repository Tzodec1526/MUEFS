export interface ExternalReceipt {
  system: string;
  reference: string;
  received_at: string;
  recorded_by: number;
  recorded_by_name: string;
  reason: string;
}

export interface PaymentRecord {
  id: number;
  amount_cents: number;
  status: string;
  transaction_ref: string | null;
  is_simulated: boolean;
  external_receipt: ExternalReceipt | null;
  created_at: string;
}

export interface PaymentRecords {
  payments: PaymentRecord[];
  total: number;
  page: number;
  payment_version: number;
}

export interface PaymentActivity {
  event_id: string;
  filing_id: number;
  event_type: 'fee_payment_recorded' | 'fee_payment_reversed';
  actor_name: string;
  occurred_at: string;
  payment_id: number;
  amount_cents: number;
  is_simulated: boolean;
  receipt_system: string;
  receipt_reference: string;
  received_at: string;
  reason: string;
}

interface RegisterTotals { credits_cents: number; reversals_cents: number }

export interface PaymentRegister {
  court_id: number;
  date_from: string;
  date_to: string;
  timezone: string;
  range_start: string;
  range_end: string;
  generated_at: string;
  include_simulated: boolean;
  total: number;
  page: number;
  totals: RegisterTotals;
  simulated_totals: RegisterTotals;
  entries: PaymentActivity[];
}
