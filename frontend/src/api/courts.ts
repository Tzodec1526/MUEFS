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
}): Promise<{ courts: Court[]; total: number }> {
  const { data } = await apiClient.get('/courts', { params });
  return data;
}

export async function getCourt(courtId: number): Promise<Court> {
  const { data } = await apiClient.get(`/courts/${courtId}`);
  return data;
}

export async function getCaseTypes(courtId: number): Promise<CaseType[]> {
  const { data } = await apiClient.get(`/courts/${courtId}/case-types`);
  return data;
}

export async function getFilingRequirements(
  courtId: number,
  caseTypeId: number,
  filingType?: string
): Promise<FilingRequirement[]> {
  const { data } = await apiClient.get(
    `/courts/${courtId}/case-types/${caseTypeId}/requirements`,
    filingType ? { params: { filing_type: filingType } } : undefined
  );
  return data;
}

export interface FilingChecklist {
  id: number;
  motion_type: string;
  checklist_items: { items: Array<{ label: string; required: boolean }> };
  help_text: string | null;
  mcr_url: string | null;
}

export async function getFilingChecklists(
  courtId: number,
  caseTypeId: number
): Promise<FilingChecklist[]> {
  const { data } = await apiClient.get(
    `/courts/${courtId}/case-types/${caseTypeId}/checklist`
  );
  return data;
}
