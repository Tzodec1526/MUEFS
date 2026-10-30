import { CanceledError } from 'axios';
import { isCurrentSession, sessionSnapshot, type SessionSnapshot } from '../auth/keycloak';
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

interface DirectoryRequest {
  session: SessionSnapshot;
  controller: AbortController;
  callers: number;
  entries: Promise<CourtDirectoryEntry[]>;
}

let directory: DirectoryRequest | undefined;

function requestDirectory(): DirectoryRequest {
  directory?.controller.abort();
  const controller = new AbortController();
  const session = sessionSnapshot();
  const request: DirectoryRequest = {
    session, controller, callers: 0,
    entries: apiClient.get<CourtDirectoryEntry[]>('/courts/directory', { signal: controller.signal }).then(({ data }) => data),
  };
  request.entries.catch(() => { if (directory === request) directory = undefined; });
  directory = request;
  return request;
}

export function listCourtDirectory(signal?: AbortSignal): Promise<CourtDirectoryEntry[]> {
  if (signal?.aborted) return Promise.reject(new CanceledError());
  const request = directory && isCurrentSession(directory.session) ? directory : requestDirectory();
  request.callers += 1;
  return new Promise((resolve, reject) => {
    const leave = () => {
      reject(new CanceledError());
      request.callers -= 1;
      if (request.callers > 0) return;
      request.controller.abort();
      if (directory === request) directory = undefined;
    };
    signal?.addEventListener('abort', leave, { once: true });
    request.entries.then(resolve, reject).finally(() => signal?.removeEventListener('abort', leave));
  });
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

