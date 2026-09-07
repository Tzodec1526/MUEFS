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
