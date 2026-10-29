import { apiClient } from './client';

export interface Court {
  id: number;
  name: string;
  county: string;
  court_type: string;
  division: string | null;
  address: string | null;
  city: string | null;
  state: string;
  zip_code: string | null;
  phone: string | null;
  cms_type: string | null;
  is_efiling_enabled: boolean;
}

export type CourtDirectoryEntry = Pick<Court, 'id' | 'name' | 'county'>;

export async function listCourtDirectory(signal?: AbortSignal): Promise<CourtDirectoryEntry[]> {
  const { data } = await apiClient.get('/courts/directory', { signal });
  return data;
}

export interface CaseType {
  id: number;
  court_id: number;
  code: string;
  name: string;
  category: string;
  filing_fee_cents: number;
  description: string | null;
  is_active: boolean;
}

export interface FilingRequirement {
  id: number;
  document_type_code: string;
  is_required: boolean;
  description: string;
  mcr_reference: string | null;
  local_rule_reference: string | null;
  page_limit: number | null;
  format_notes: string | null;
}

export async function listCourts(params?: {
  county?: string;
  court_type?: string;
  tier?: string;
  q?: string;
  page?: number;
  page_size?: number;
}, signal?: AbortSignal): Promise<{ courts: Court[]; total: number }> {
  const { data } = await apiClient.get('/courts', { params, signal });
  return data;
}

export async function getCourt(courtId: number): Promise<Court> {
  const { data } = await apiClient.get(`/courts/${courtId}`);
  return data;
}

export async function getCaseTypes(courtId: number, includeInactive = false, signal?: AbortSignal): Promise<CaseType[]> {
  const { data } = await apiClient.get(`/courts/${courtId}/case-types`, {
    params: includeInactive ? { include_inactive: true } : undefined,
    signal,
  });
  return data;
}

export async function getFilingRequirements(
  courtId: number,
  caseTypeId: number,
  filingType?: string,
  signal?: AbortSignal,
): Promise<FilingRequirement[]> {
  const { data } = await apiClient.get(
    `/courts/${courtId}/case-types/${caseTypeId}/requirements`,
    { params: filingType ? { filing_type: filingType } : undefined, signal },
  );
  return data;
}

