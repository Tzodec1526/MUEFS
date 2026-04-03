import { apiClient } from './client';

export async function searchCases(params: {
  case_number?: string;
  party_name?: string;
  court_id?: number;
  page?: number;
}) {
  const { data } = await apiClient.get('/cases/search', { params });
  return data;
}

export async function getCase(caseId: number) {
  const { data } = await apiClient.get(`/cases/${caseId}`);
  return data;
}

export async function calculateFees(
  courtId: number,
  caseTypeId: number,
  documentCount: number = 1,
) {
  const { data } = await apiClient.post('/payments/calculate', {
    court_id: courtId,
    case_type_id: caseTypeId,
    document_count: documentCount,
  });
  return data;
}
