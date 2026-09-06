import { apiClient } from './client';

export interface FilingDocument {
  id: number;
  document_type_code: string;
  title: string;
  file_size_bytes: number;
  mime_type: string;
  page_count: number | null;
  sha256_hash: string;
  is_confidential: boolean;
  is_text_searchable: boolean;
  uploaded_at: string;
}

export interface FilingEnvelope {
  id: number;
  court_id: number;
  case_id: number | null;
  case_type_id: number;
  filer_id: number;
  filing_type: 'initial' | 'subsequent' | 'service_only';
  status: string;
  payment_id: number | null;
  case_title: string | null;
  filing_description: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  fee_waiver_requested: boolean;
  fee_waiver_granted: boolean | null;
  fee_waiver_reason: string | null;
  fee_waiver_referred_at: string | null;
  fee_waiver_decided_at: string | null;
  fee_waiver_amount_due_cents: number | null;
  documents: FilingDocument[];
  created_at: string;
  updated_at: string;
  submission_count: number;
  filing_date: string | null;
  filing_date_basis: FilingDateBasis | null;
}

export interface FilingValidation {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  missing_required_documents: string[];
}

export async function createFiling(data: {
  court_id: number;
  case_id?: number;
  case_type_id: number;
  filing_type?: string;
  case_title?: string;
  filing_description?: string;
  fee_waiver_requested?: boolean;
  fee_waiver_reason?: string;
}): Promise<FilingEnvelope> {
  const response = await apiClient.post('/filings', data);
  return response.data;
}

export async function listFilings(params?: {
  status?: string;
  page?: number;
}, signal?: AbortSignal): Promise<{
  filings: FilingEnvelope[];
  total: number;
  status_counts: Record<string, number>;
  court_names: Record<number, string>;
}> {
  const { data } = await apiClient.get('/filings', { params, signal });
  return data;
}

export async function getFilingStatusCounts(): Promise<Record<string, number>> {
  const { data } = await apiClient.get('/filings/summary');
  return data;
}

export async function getFiling(filingId: number, signal?: AbortSignal): Promise<FilingEnvelope> {
  const { data } = await apiClient.get(`/filings/${filingId}`, { signal });
  return data;
}

export async function updateFiling(
  filingId: number,
  patch: {
    case_title?: string;
    filing_description?: string;
    fee_waiver_requested?: boolean;
    fee_waiver_reason?: string;
  }
): Promise<FilingEnvelope> {
  const { data } = await apiClient.patch(`/filings/${filingId}`, patch);
  return data;
}

export async function validateFiling(filingId: number): Promise<FilingValidation> {
  const { data } = await apiClient.post(`/filings/${filingId}/validate`);
  return data;
}

export async function submitFiling(filingId: number, idempotencyKey?: string): Promise<FilingEnvelope> {
  const { data } = await apiClient.post(`/filings/${filingId}/submit`, undefined, {
    headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
  });
  return data;
}

export interface FilingTransaction {
  id: string;
  submission_number: number;
  event_type: string;
  actor_name: string;
  occurred_at: string;
  details: {
    reason?: string;
    court_name?: string;
    case_title?: string | null;
    case_number?: string | null;
    filing_description?: string | null;
    fee_waiver_requested?: boolean;
    payment?: { amount_cents: number; transaction_ref: string; is_simulated: boolean } | null;
    basis?: string;
    amount_due_cents?: number;
    filing_date_basis?: FilingDateBasis | null;
    previous_filing_date?: string | null;
    case_date_change?: { case_id: number; case_number: string; previous_filing_date: string | null; filing_date: string };
    documents?: FilingDocument[];
    document_id?: number;
    public_copy?: { id: number; title: string; sha256_hash: string; file_size_bytes: number };
    cms_case_number?: string | null;
    cms_filing_id?: string | null;
  };
}

export interface FilingHistory {
  filing_id: number;
  status: string;
  submission_count: number;
  transactions: FilingTransaction[];
  total: number;
  page: number;
  page_size: number;
  fee_waiver: FeeWaiverState | null;
  filing_date: string | null;
  filing_date_basis: FilingDateBasis | null;
  court_id: number;
  can_manage_documents: boolean;
}

export interface FilingDateAssessment {
  source?: never;
  filing_date: string | null;
  timezone: string | null;
  local_received_date: string | null;
  calendar_ids: number[];
  skipped_dates: Record<string, string>;
  error: string | null;
}

export type FilingDateBasis = FilingDateAssessment | {
  source: 'court_order';
  filing_date: string;
  order_document_id: number;
  order_signed_date: string;
  authority_reference: string;
  submission_number: number;
};

export interface FeeWaiverState {
  granted: boolean | null;
  referred_at: string | null;
  decided_at: string | null;
  amount_due_cents: number | null;
  payment_id: number | null;
  can_pay: boolean;
  payments_simulated: boolean;
  allowed_actions: string[];
}

export async function decideFeeWaiver(filingId: number, decision: FormData): Promise<void> {
  await apiClient.post(`/clerk/filings/${filingId}/fee-waiver`, decision, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

export async function getFilingHistory(filingId: number, page: number, signal?: AbortSignal): Promise<FilingHistory> {
  const { data } = await apiClient.get(`/filings/${filingId}/history`, { params: { page }, signal });
  return data;
}

export interface DocumentUploadResult {
  id: number;
  title: string;
  file_size_bytes: number;
  mime_type: string;
  sha256_hash: string;
  is_text_searchable: boolean;
  page_count: number | null;
  warnings: string[];
}

export async function uploadDocument(
  filingId: number,
  file: File,
  documentTypeCode: string,
  title: string,
  isConfidential: boolean = false,
): Promise<DocumentUploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('document_type_code', documentTypeCode);
  formData.append('title', title);
  formData.append('is_confidential', String(isConfidential));

  const { data } = await apiClient.post(`/filings/${filingId}/documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function removeDocument(
  filingId: number,
  documentId: number
): Promise<void> {
  await apiClient.delete(`/filings/${filingId}/documents/${documentId}`);
}

export async function reviewFiling(
  filingId: number,
  action: 'accept' | 'reject' | 'return',
  reason?: string,
): Promise<FilingEnvelope> {
  const { data } = await apiClient.post(`/clerk/filings/${filingId}/review`, {
    action,
    reason,
  });
  return data;
}

export async function getClerkQueue(
  courtId: number,
  page: number = 1,
  statusFilter?: string,
  signal?: AbortSignal,
): Promise<{ filings: FilingEnvelope[]; total: number }> {
  const params: Record<string, unknown> = { court_id: courtId, page };
  if (statusFilter === 'waivers') {
    params.fee_waivers = true;
  } else if (statusFilter && statusFilter !== 'all') {
    params.status = statusFilter;
  }
  const { data } = await apiClient.get('/clerk/queue', { params, signal });
  return data;
}

export async function batchReview(
  filingIds: number[],
  action: 'accept',
): Promise<{ succeeded: number[]; failed: number[] }> {
  const { data } = await apiClient.post('/clerk/queue/batch-review', {
    filing_ids: filingIds,
    action,
  });
  return data;
}
