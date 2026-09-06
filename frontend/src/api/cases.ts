import { apiClient } from './client';

export const participantRoles: Record<string, string> = {
  plaintiff: 'Plaintiff', defendant: 'Defendant', petitioner: 'Petitioner', respondent: 'Respondent',
  attorney_plaintiff: 'Attorney (Plaintiff)', attorney_defendant: 'Attorney (Defendant)',
  attorney: 'Attorney', guardian: 'Guardian', intervenor: 'Intervenor',
};

export interface CaseSearchResult {
  id: number;
  case_number: string;
  case_type_id: number;
  title: string;
  status: string;
  court_id: number;
  court_name: string;
  court_county: string;
  filed_date: string;
  filing_date: string | null;
  participants: Array<{
    party_name: string;
    role: string;
    attorney_bar_number?: string | null;
  }>;
}

export async function searchCases(params: {
  case_number?: string;
  party_name?: string;
  court_id?: number;
  page?: number;
}, signal?: AbortSignal): Promise<{ cases: CaseSearchResult[]; total: number; page: number; page_size: number }> {
  const { data } = await apiClient.get('/cases/search', { params, signal });
  return data;
}

export async function getCase(caseId: number) {
  const { data } = await apiClient.get(`/cases/${caseId}`);
  return data;
}
