import { useEffect, useState } from 'react';
import type { FilingEnvelope } from '../../api/filings';
import {
  filingDraftKey, loadFilingDraft, saveFilingDraft, clearFilingDraft, type FilingDraft,
} from '../../utils/filingDraft';

export interface FilingData extends FilingDraft {
  documents: Array<{ id: number; title: string; type: string; size: number; isSearchable: boolean }>;
}

export const defaultFilingData: FilingData = {
  courtId: null,
  courtName: '',
  caseId: null,
  filingType: 'initial',
  caseTypeId: null,
  caseTypeName: '',
  caseTitle: '',
  filingDescription: '',
  filingId: null,
  detailsToken: null,
  documents: [],
  caseChoiceMade: false,
};

function initialFilingData(draft: FilingDraft | null, requestedFilingId: string | null, searchParams: URLSearchParams): FilingData {
  if (draft || requestedFilingId) return { ...defaultFilingData, ...draft };
  const courtId = searchParams.get('court_id');
  if (!courtId) return defaultFilingData;
  const caseId = searchParams.get('case_id');
  const caseTypeId = searchParams.get('case_type_id');
  if (!caseId || !caseTypeId) return { ...defaultFilingData, courtId: Number(courtId) };
  const serviceOnly = searchParams.get('service_only') === 'true';
  return {
    ...defaultFilingData,
    courtId: Number(courtId),
    caseId: Number(caseId),
    caseTypeId: Number(caseTypeId),
    filingType: serviceOnly ? 'service_only' : 'subsequent',
    caseChoiceMade: true,
  };
}

export function useFilingDraft(userId: number, searchParams: URLSearchParams, { loadedFiling, submission, paused }: {
  loadedFiling: FilingEnvelope | null; submission: FilingEnvelope | undefined; paused: boolean;
}) {
  const requestedFilingId = searchParams.get('filing_id');
  const draftKey = filingDraftKey(userId, requestedFilingId || `new:${searchParams.toString()}`);
  const [draft] = useState(() => loadFilingDraft(draftKey));
  const [filingData, setFilingData] = useState<FilingData>(() => initialFilingData(draft, requestedFilingId, searchParams));
  const [recoveryAvailable, setRecoveryAvailable] = useState(true);
  const dirty = !submission && (filingData.filingId
    ? loadedFiling !== null && (filingData.caseTitle !== (loadedFiling.case_title ?? '')
      || filingData.filingDescription !== (loadedFiling.filing_description ?? ''))
    : filingData.courtId !== null);

  useEffect(() => {
    if (paused) return;
    if (dirty) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- expose whether external recovery storage accepted the current edit
      setRecoveryAvailable(saveFilingDraft(draftKey, filingData));
    } else {
      clearFilingDraft(draftKey);
    }
  }, [draftKey, filingData, dirty, paused]);

  useEffect(() => {
    if (!dirty) return;
    const warnBeforeClose = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnBeforeClose);
    return () => window.removeEventListener('beforeunload', warnBeforeClose);
  }, [dirty]);

  return { draftKey, draft, filingData, setFilingData, dirty, recoveryAvailable, setRecoveryAvailable };
}
