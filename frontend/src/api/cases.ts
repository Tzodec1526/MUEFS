import { apiClient } from './client';

export const participantRoles: Record<string, string> = {
  plaintiff: 'Plaintiff', defendant: 'Defendant', petitioner: 'Petitioner', respondent: 'Respondent',
  attorney_plaintiff: 'Attorney (Plaintiff)', attorney_defendant: 'Attorney (Defendant)',
  attorney: 'Attorney', guardian: 'Guardian', intervenor: 'Intervenor',
};

export async function searchCases(params: {
  case_number?: string;
  party_name?: string;
  court_id?: number;
  page?: number;
}, signal?: AbortSignal) {
  const { data } = await apiClient.get('/cases/search', { params, signal });
  return data;
}

export async function getCase(caseId: number) {
  const { data } = await apiClient.get(`/cases/${caseId}`);
  return data;
}
