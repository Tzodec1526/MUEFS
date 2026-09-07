import type { FilingEnvelope } from '../api/filings';

// Only unsaved form fields belong here. Documents, fees and saved filing state come from the API.
export interface FilingDraft {
  courtId: number | null;
  courtName: string;
  caseId: number | null;
  filingType: 'initial' | 'subsequent' | 'service_only';
  caseTypeId: number | null;
  caseTypeName: string;
  caseTitle: string;
  filingDescription: string;
  filingId: number | null;
  creationKey?: string;
  detailsToken: string | null;
  caseChoiceMade: boolean;
}

const PREFIX = 'muefs_filing_draft:v2:';

export function filingDraftKey(userId: number, scope: string): string {
  return `${PREFIX}${userId}:${scope}`;
}

export function loadFilingDraft(key: string): FilingDraft | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const draft = JSON.parse(raw);
    if (!draft || typeof draft !== 'object'
      || !['initial', 'subsequent', 'service_only'].includes(draft.filingType)
      || !['courtId', 'caseId', 'caseTypeId', 'filingId'].every(field =>
        draft[field] === null || (Number.isSafeInteger(draft[field]) && draft[field] > 0))
      || !['courtName', 'caseTypeName', 'caseTitle', 'filingDescription'].every(field => typeof draft[field] === 'string')
      || typeof draft.caseChoiceMade !== 'boolean'
      || !(draft.creationKey === undefined || (typeof draft.creationKey === 'string'
        && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(draft.creationKey)))
      || !(draft.detailsToken === null || (typeof draft.detailsToken === 'string' && /^[0-9a-f]{64}$/.test(draft.detailsToken)))) return null;
    return draft;
  } catch { return null; }
}

export function saveFilingDraft(key: string, data: FilingDraft): boolean {
  try {
    const draft: FilingDraft = {
      courtId: data.courtId, courtName: data.courtName, caseId: data.caseId,
      filingType: data.filingType, caseTypeId: data.caseTypeId, caseTypeName: data.caseTypeName,
      caseTitle: data.caseTitle, filingDescription: data.filingDescription,
      filingId: data.filingId, detailsToken: data.detailsToken,
      creationKey: data.creationKey,
      caseChoiceMade: data.caseChoiceMade,
    };
    sessionStorage.setItem(key, JSON.stringify(draft));
    return true;
  } catch { return false; }
}

export function clearFilingDraft(key: string, filingId?: number): void {
  try { sessionStorage.removeItem(key); } catch { /* Saving through the API still works. */ }
  try {
    if (filingId && JSON.parse(localStorage.getItem('muefs_filing_draft') || 'null')?.filingId === filingId) {
      localStorage.removeItem('muefs_filing_draft');
    }
  } catch { /* Leave unrecognized legacy recovery data untouched. */ }
}

export function clearFilingDrafts(): void {
  try {
    for (const key of Object.keys(sessionStorage)) {
      if (key.startsWith(PREFIX)) sessionStorage.removeItem(key);
    }
  } catch { /* Storage may be disabled. */ }
}

// An old, unscoped entry is offered only after the server verifies ownership of its saved filing.
// Its base version is unknown, so the user must compare it before reusing any edits.
export function loadLegacyFilingDraft(userId: number, filing: Pick<FilingEnvelope, 'id' | 'filer_id'>) {
  if (filing.filer_id !== userId) return null;
  try {
    const draft = JSON.parse(localStorage.getItem('muefs_filing_draft') || 'null');
    if (draft?.filingId !== filing.id || typeof draft.caseTitle !== 'string'
      || typeof draft.filingDescription !== 'string') return null;
    return { caseTitle: draft.caseTitle, filingDescription: draft.filingDescription,
      detailsToken: null };
  } catch { return null; }
}
