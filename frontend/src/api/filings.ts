import { apiClient } from './client';
import type { ExternalReceipt } from './payments';

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
  submission_token: string;
  details_token: string;
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

export type FilingSummary = Pick<FilingEnvelope,
  'id' | 'court_id' | 'case_id' | 'filer_id' | 'status' | 'case_title' |
  'filing_description' | 'submitted_at' | 'rejection_reason' |
  'fee_waiver_requested' | 'fee_waiver_granted' | 'created_at' |
  'updated_at' | 'submission_count'
> & { document_count: number };

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
}, creationKey: string): Promise<FilingEnvelope> {
  const response = await apiClient.post('/filings', data, { headers: { 'Idempotency-Key': creationKey } });
  return response.data;
}

export async function listFilings(params?: {
  status?: string;
  page?: number;
}, signal?: AbortSignal): Promise<{
  filings: FilingSummary[];
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
    expected_details_token?: string;
    case_title?: string;
    filing_description?: string;
    fee_waiver_requested?: boolean;
    fee_waiver_reason?: string;
  }
): Promise<FilingEnvelope> {
  const { data } = await apiClient.patch(`/filings/${filingId}`, patch);
  return data;
}

export async function validateFiling(filingId: number, signal?: AbortSignal): Promise<FilingValidation> {
  const { data } = await apiClient.post(`/filings/${filingId}/validate`, undefined, { signal });
  return data;
}

export async function submitFiling(
  filingId: number, expectedSubmissionToken: string, idempotencyKey: string,
): Promise<FilingEnvelope> {
  const { data } = await apiClient.post(`/filings/${filingId}/submit`, {
    expected_submission_token: expectedSubmissionToken,
  }, {
    headers: { 'Idempotency-Key': idempotencyKey },
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
    payment?: {
      amount_cents: number; transaction_ref: string; is_simulated: boolean;
      external_receipt?: ExternalReceipt | null;
      fee_basis?: { source: string; assessment_id: string | null; total_cents: number; previous_paid_cents: number };
    } | null;
    payments?: Array<{ id: number; amount_cents: number; transaction_ref: string; is_simulated: boolean; status: string; external_receipt?: ExternalReceipt | null }>;
    fee_assessment?: { source: string; assessment_id: string | null; total_cents: number | null; paid_cents: number; balance_due_cents: number | null };
    basis?: string;
    amount_due_cents?: number;
    items?: Array<{ fee_type: string; amount_cents: number; description: string }>;
    total_cents?: number;
    authority_reference?: string;
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
  balance_due_cents: number | null;
  fee_version: number;
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

interface DocumentUploadResult {
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
  uploadKey: string,
  isConfidential: boolean = false,
): Promise<DocumentUploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('document_type_code', documentTypeCode);
  formData.append('title', title);
  formData.append('is_confidential', String(isConfidential));

  const { data } = await apiClient.post(`/filings/${filingId}/documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data', 'Idempotency-Key': uploadKey },
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
  filing: Pick<FilingEnvelope, 'id' | 'submission_count'>,
  action: 'accept' | 'reject' | 'return',
  reason?: string,
): Promise<FilingEnvelope> {
  const { data } = await apiClient.post(`/clerk/filings/${filing.id}/review`, {
    action,
    reason,
    expected_submission_count: filing.submission_count,
  });
  return data;
}

export interface ClerkQueue {
  filings: FilingSummary[];
  total: number;
  page_size: number;
  submitted_count: number;
  under_review_count: number;
  waiting_48h: number;
  oldest_submitted_at: string | null;
  as_of: string;
}

export interface ClerkQueueFilters {
  status?: string;
  search?: string;
  waiting_48h_only?: boolean;
}

export async function getClerkQueue(courtId: number, options: ClerkQueueFilters & {
  page?: number; page_size?: number; signal?: AbortSignal;
} = {}): Promise<ClerkQueue> {
  const { status, signal, ...filters } = options;
  const params: Record<string, unknown> = { court_id: courtId, page: 1, page_size: 25, ...filters };
  if (status === 'waivers') {
    params.fee_waivers = true;
  } else if (status && status !== 'all') {
    params.status = status;
  }
  const { data } = await apiClient.get('/clerk/queue', { params, signal });
  return data;
}

export async function batchReview(
  filings: Pick<FilingEnvelope, 'id' | 'submission_count'>[],
  action: 'accept',
): Promise<{ succeeded: number[]; failed: number[]; errors: Record<number, string> }> {
  const { data } = await apiClient.post('/clerk/queue/batch-review', {
    filings: filings.map(filing => ({
      filing_id: filing.id,
      expected_submission_count: filing.submission_count,
    })),
    action,
  });
  return data;
}
