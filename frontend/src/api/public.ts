import { apiClient } from './client';

export interface PublicPlatformStats {
  courts_efiling_enabled: number;
  public_cases_indexed: number;
  total_filings: number;
  pending_clerk_review: number;
  mcr_document_types: number;
  max_upload_mb: number;
  mifile_max_upload_mb: number;
}

export async function getPublicStats(): Promise<PublicPlatformStats> {
  const { data } = await apiClient.get<PublicPlatformStats>('/public/stats');
  return data;
}
