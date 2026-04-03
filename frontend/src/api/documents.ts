import { apiClient } from './client';

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
