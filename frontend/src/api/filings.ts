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
  status: string;
  case_title: string | null;
  filing_description: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  documents: FilingDocument[];
  created_at: string;
  updated_at: string;
}

export interface FilingValidation {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  missing_required_documents: string[];
}

export async function createFiling(data: {
  court_id: number;
  case_type_id: number;
  case_title?: string;
  filing_description?: string;
}): Promise<FilingEnvelope> {
  const response = await apiClient.post('/filings', data);
  return response.data;
}

export async function listFilings(params?: {
  status?: string;
  page?: number;
}): Promise<{ filings: FilingEnvelope[]; total: number }> {
  const { data } = await apiClient.get('/filings', { params });
  return data;
}

export async function getFiling(filingId: number): Promise<FilingEnvelope> {
  const { data } = await apiClient.get(`/filings/${filingId}`);
  return data;
}

export async function validateFiling(filingId: number): Promise<FilingValidation> {
  const { data } = await apiClient.post(`/filings/${filingId}/validate`);
  return data;
}

export async function submitFiling(filingId: number): Promise<FilingEnvelope> {
  const { data } = await apiClient.post(`/filings/${filingId}/submit`);
  return data;
}

export async function uploadDocument(
  filingId: number,
  file: File,
  documentTypeCode: string,
  title: string,
  isConfidential: boolean = false,
): Promise<FilingDocument> {
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
): Promise<{ filings: FilingEnvelope[]; total: number }> {
  const { data } = await apiClient.get('/clerk/queue', {
    params: { court_id: courtId, page },
  });
  return data;
}
