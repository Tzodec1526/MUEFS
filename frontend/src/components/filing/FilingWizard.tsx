import { useState, useEffect, useCallback, useContext, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { isAxiosError } from 'axios';
import { CourtContext } from '../auth/CourtSession';
import {
  filingDraftKey, loadFilingDraft, saveFilingDraft, clearFilingDraft, loadLegacyFilingDraft,
  type FilingDraft,
} from '../../utils/filingDraft';
import CourtSelector from './CourtSelector';
import CaseSelector, { CaseResult } from './CaseSelector';
import CaseTypeSelector from './CaseTypeSelector';
import DocumentUpload from './DocumentUpload';
import FilingReview from './FilingReview';
import { emitToast } from '../../utils/toastBus';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { createFiling, getFiling, updateFiling, type FilingEnvelope } from '../../api/filings';
import LoadError from '../common/LoadError';
import { getCase, type CaseDocket } from '../../api/cases';
import { getCourt, getCaseTypes } from '../../api/courts';
import { getDemoRole } from '../auth/LoginScreen';
import {
  hasPlainLanguagePreference,
  isPlainLanguageMode,
  setPlainLanguageMode,
  stepLabel,
} from '../../utils/srlMode';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

const CASE_LOOKUP_FAILED = "We couldn't load the court's record for this case, so its title is missing.";

type WizardStep = 'court' | 'case' | 'case-type' | 'details' | 'documents' | 'review';

interface FilingData extends FilingDraft {
  documents: Array<{ id: number; title: string; type: string; size: number; isSearchable: boolean }>;
}

// Steps adapt to the filing: a new case adds Case Type + Case Details; filing into an
// existing case skips Case Type (it's known from the case).
function buildSteps(filingType: string): { key: WizardStep; label: string }[] {
  const isNewCase = filingType === 'initial';
  return [
    { key: 'court', label: 'Select Court' },
    { key: 'case', label: 'Case' },
    ...(isNewCase
      ? [{ key: 'case-type' as WizardStep, label: 'Case Type & Rules' }]
      : []),
    { key: 'details', label: isNewCase ? 'Case Details' : 'Filing Details' },
    { key: 'documents', label: 'Documents' },
    { key: 'review', label: 'Review & Submit' },
  ];
}

const defaultFilingData: FilingData = {
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

function FilingWizard() {
  const { userId, loading, error, refresh } = useContext(CourtContext)!;
  if (loading) return <p role="status">Loading your filing workspace…</p>;
  if (!userId) return <LoadError failure={error ?? { message: 'Could not verify your account.', retry: true }} onRetry={refresh} />;
  return <FilingForm key={userId} userId={userId} />;
}

function FilingForm({ userId }: { userId: number }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedFilingId = searchParams.get('filing_id');
  usePageTitle(requestedFilingId ? `Filing #${requestedFilingId}` : 'New filing');
  const draftKey = filingDraftKey(userId, requestedFilingId || `new:${searchParams.toString()}`);
  const [draft] = useState(() => loadFilingDraft(draftKey));
  const [filingData, setFilingData] = useState<FilingData>(() => {
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
  });
  const [currentStep, setCurrentStep] = useState<WizardStep>(() =>
    draft?.creationKey ? 'details' : draft ? 'court' : filingData.caseId ? 'details' : filingData.courtId ? 'case' : 'court'
  );
  const [showDraftBanner, setShowDraftBanner] = useState(!!draft);
  const [saving, setSaving] = useState(false);
  const [loadedFiling, setLoadedFiling] = useState<FilingEnvelope | null>(null);
  const readOnly = loadedFiling !== null && !['draft', 'returned'].includes(loadedFiling.status);
  const [loadingExisting, setLoadingExisting] = useState(Boolean(requestedFilingId));
  const [loadError, setLoadError] = useState<LoadFailure | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [submission, setSubmission] = useState<FilingEnvelope>();
  const [errors, setErrors] = useState<string[]>([]);
  const conflictHeading = useRef<HTMLHeadingElement>(null);
  const [conflict, setConflict] = useState<FilingEnvelope | null>(null);
  const [saveNotice, setSaveNotice] = useState('');
  const [recoveryAvailable, setRecoveryAvailable] = useState(true);
  const [creationConflictId, setCreationConflictId] = useState<number | null>(null);
  const destinationLocked = filingData.filingId !== null || Boolean(filingData.creationKey);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const dirty = !submission && (filingData.filingId
    ? loadedFiling !== null && (filingData.caseTitle !== (loadedFiling.case_title ?? '')
      || filingData.filingDescription !== (loadedFiling.filing_description ?? ''))
    : filingData.courtId !== null);
  const handleFeesChange = useCallback((filing: FilingEnvelope) => {
    setFilingData(prev => ({ ...prev,
      detailsToken: prev.caseTitle === (filing.case_title ?? '')
        && prev.filingDescription === (filing.filing_description ?? '')
        ? filing.details_token : prev.detailsToken,
      documents: filing.documents.map(doc => ({ id: doc.id, title: doc.title,
        type: doc.document_type_code, size: doc.file_size_bytes, isSearchable: doc.is_text_searchable })),
    }));
  }, []);
  const isMotionMode = filingData.filingType !== 'initial';
  const [plainLanguage, setPlainLanguage] = useState(() => {
    // Self-represented filers start in plain language, but a filer who turned it off keeps it off.
    if (getDemoRole() === 'srl' && !hasPlainLanguagePreference()) setPlainLanguageMode(true);
    return isPlainLanguageMode();
  });
  // Why a case-linked filing has no caption yet: the court's case record did not load.
  const [caseLookupError, setCaseLookupError] = useState<LoadFailure | null>(null);

  // Load the saved envelope, or resolve display labels for a new filing's URL prefill.
  useEffect(() => {
    const filingId = requestedFilingId;
    if (filingId) {
      const controller = new AbortController();
      const loadExisting = async () => {
        setLoadingExisting(true);
        setLoadError(null);
        try {
          const envelope = await getFiling(Number(filingId), controller.signal);
          const [court, types] = await Promise.all([
            getCourt(envelope.court_id),
            getCaseTypes(envelope.court_id, true), // Preserve disabled case-type labels on saved records.
          ]);
          if (controller.signal.aborted) return;
          const caseType = types.find((type) => type.id === envelope.case_type_id);
          const filingType = envelope.filing_type === 'initial' || envelope.filing_type === 'service_only'
            ? envelope.filing_type : 'subsequent';
          const savedDraft = draft?.filingId === envelope.id ? draft
            : loadLegacyFilingDraft(userId, envelope);
          const recoveredDraft = savedDraft && (savedDraft.caseTitle !== (envelope.case_title ?? '')
            || savedDraft.filingDescription !== (envelope.filing_description ?? '')) ? savedDraft : null;
          const stale = recoveredDraft && recoveredDraft.detailsToken !== envelope.details_token;
          setConflict(stale ? envelope : null);
          setLoadedFiling(envelope);
          setFilingData({
            ...defaultFilingData,
            filingId: envelope.id,
            detailsToken: recoveredDraft ? recoveredDraft.detailsToken : envelope.details_token,
            courtId: envelope.court_id,
            courtName: court.name,
            caseId: envelope.case_id,
            caseTypeId: envelope.case_type_id,
            caseTypeName: caseType?.name || '',
            filingType,
            caseTitle: recoveredDraft?.caseTitle ?? envelope.case_title ?? '',
            filingDescription: recoveredDraft?.filingDescription ?? envelope.filing_description ?? '',
            caseChoiceMade: true,
            documents: envelope.documents.map((doc) => ({
              id: doc.id, title: doc.title, type: doc.document_type_code,
              size: doc.file_size_bytes, isSearchable: doc.is_text_searchable,
            })),
          });
          setCurrentStep(recoveredDraft || searchParams.get('step') === 'details' ? 'details' : 'documents');
          setShowDraftBanner(recoveredDraft !== null);
        } catch (err) {
          if (!controller.signal.aborted) {
            setLoadError(loadFailure(err, 'Could not load this filing. Please retry.'));
          }
        } finally {
          if (!controller.signal.aborted) setLoadingExisting(false);
        }
      };
      loadExisting();
      return () => controller.abort();
    }
    const courtId = searchParams.get('court_id');
    if (!courtId) return;
    const caseTypeId = searchParams.get('case_type_id');
    const caseId = searchParams.get('case_id');
    let active = true;
    type CaseLookup = { docket: CaseDocket | null; failure?: LoadFailure };
    Promise.all([
      getCourt(Number(courtId)).catch(() => ({ name: `Court #${courtId}` })),
      // A display label for an existing case: keep it after the court closes the type to new cases.
      caseTypeId ? getCaseTypes(Number(courtId), true).catch(() => []) : Promise.resolve([]),
      // The court's case record, not the link, names the case being filed into.
      caseId
        ? getCase(Number(caseId)).then(
          (docket): CaseLookup => ({ docket }),
          (err: unknown): CaseLookup => ({ docket: null, failure: loadFailure(err, CASE_LOOKUP_FAILED) }))
        : Promise.resolve<CaseLookup>({ docket: null }),
    ]).then(([court, types, { docket, failure }]) => {
      if (!active) return;
      setFilingData(prev => prev.courtId !== Number(courtId) ? prev : {
        ...prev,
        courtName: court.name,
        caseTypeName: types.find(t => t.id === prev.caseTypeId)?.name || prev.caseTypeName,
        caseTitle: docket && prev.caseId === docket.id ? docket.title : prev.caseTitle,
      });
      setCaseLookupError(failure ?? null);
    });
    return () => { active = false; };
  }, [searchParams, requestedFilingId, draft, reloadKey, userId]);

  const steps = buildSteps(filingData.filingType).map((s) => ({
    ...s,
    label: plainLanguage ? stepLabel(s.key, s.label) : s.label,
  }));
  const currentStepIndex = steps.findIndex((s) => s.key === currentStep);
  const detailsStepIndex = steps.findIndex((s) => s.key === 'details');

  const updateData = (updates: Partial<FilingData>) => {
    setSaveNotice('');
    setErrors([]);
    setFilingData((prev) => ({ ...prev, ...updates }));
  };

  useEffect(() => {
    if (loadingExisting || loadError || readOnly || submission) return;
    if (dirty) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- expose whether external recovery storage accepted the current edit
      setRecoveryAvailable(saveFilingDraft(draftKey, filingData));
    } else {
      clearFilingDraft(draftKey);
    }
  }, [draftKey, filingData, dirty, loadingExisting, loadError, readOnly, submission]);

  useEffect(() => {
    if (!dirty) return;
    const warnBeforeClose = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnBeforeClose);
    return () => window.removeEventListener('beforeunload', warnBeforeClose);
  }, [dirty]);

  async function saveDetails(advance = false): Promise<boolean> {
    if (conflict || !filingData.caseTitle.trim()) return false;
    setSaving(true);
    setErrors([]);
    setSaveNotice('');
    try {
      let creationKey = filingData.creationKey;
      if (!filingData.filingId) {
        creationKey ??= crypto.randomUUID();
        const pending = { ...filingData, creationKey };
        setFilingData(pending);
        // Persist before sending: a response can be lost even when the server commits.
        setRecoveryAvailable(saveFilingDraft(draftKey, pending));
      }
      const filing = filingData.filingId
        ? await updateFiling(filingData.filingId, {
          expected_details_token: filingData.detailsToken!,
          case_title: filingData.caseTitle, filing_description: filingData.filingDescription,
        })
        : await createFiling({
          court_id: filingData.courtId!, case_id: filingData.caseId || undefined,
          case_type_id: filingData.caseTypeId!, filing_type: filingData.filingType,
          case_title: filingData.caseTitle, filing_description: filingData.filingDescription,
        }, creationKey!);
      // Leaving the workspace must not clear recovery or navigate a different account.
      if (!mounted.current) return false;
      setLoadedFiling(filing);
      setFilingData(previous => ({ ...previous, filingId: filing.id, detailsToken: filing.details_token }));
      clearFilingDraft(draftKey, filing.id);
      setShowDraftBanner(false);
      setSaveNotice('Draft saved to your account. You can continue it from My Filings.');
      if (!filingData.filingId) {
        emitToast('Draft saved to your account. Continue it from My Filings.', 'success');
        setSearchParams({ filing_id: String(filing.id), step: advance ? 'documents' : 'details' }, { replace: true });
      }
      return true;
    } catch (err) {
      if (!mounted.current) return false;
      setErrors([errorMessage(err, 'Could not save your filing. Your edits are still here.')]);
      if (!filingData.filingId && isAxiosError(err) && err.response?.status === 409) {
        const existingId: unknown = err.response.data?.filing_id;
        if (typeof existingId === 'number' && Number.isSafeInteger(existingId) && existingId > 0) {
          const recovered = { ...filingData, filingId: existingId, detailsToken: null, creationKey: undefined };
          if (saveFilingDraft(filingDraftKey(userId, String(existingId)), recovered)) {
            clearFilingDraft(draftKey);
            setSearchParams({ filing_id: String(existingId), step: 'details' }, { replace: true });
          } else {
            setRecoveryAvailable(false);
            setCreationConflictId(existingId);
          }
        }
      }
      if (filingData.filingId && isAxiosError(err) && err.response?.status === 409) {
        try {
          const latest = await getFiling(filingData.filingId);
          if (mounted.current) { setConflict(latest); setErrors([]); }
        }
        catch { /* Keep the edits and original precondition if comparison cannot load. */ }
      }
      return false;
    } finally { if (mounted.current) setSaving(false); }
  }

  function resolveConflict(keepEdits: boolean) {
    if (!conflict) return;
    setLoadedFiling(conflict);
    setFilingData(previous => ({ ...previous, detailsToken: conflict.details_token,
      ...(!keepEdits ? { caseTitle: conflict.case_title ?? '', filingDescription: conflict.filing_description ?? '' } : {}),
    }));
    if (!keepEdits) clearFilingDraft(draftKey, conflict.id);
    setConflict(null);
    setErrors([]);
    setShowDraftBanner(false);
    setSaveNotice(keepEdits ? 'Your edits are ready. Save draft or Continue to save them to your account.' : 'Showing the saved details.');
  }

  const canProceed = (): boolean => {
    switch (currentStep) {
      case 'court':
        return filingData.courtId !== null;
      case 'case':
        return filingData.caseChoiceMade;
      case 'case-type':
        return filingData.caseTypeId !== null;
      case 'details':
        return filingData.caseTitle.trim().length > 0;
      case 'documents':
        return filingData.documents.length > 0;
      default:
        return true;
    }
  };

  const goNext = async () => {
    setErrors([]);
    if (!canProceed()) {
      setErrors([getStepError()]);
      return;
    }

    if (currentStep === 'details' && !await saveDetails(true)) return;

    if (currentStepIndex < steps.length - 1) {
      setCurrentStep(steps[currentStepIndex + 1].key);
      window.scrollTo(0, 0);
      document.getElementById('main-content')?.focus();
    }
  };

  const goBack = () => {
    setErrors([]);
    if (currentStepIndex > 0) {
      setCurrentStep(steps[currentStepIndex - 1].key);
      window.scrollTo(0, 0);
      document.getElementById('main-content')?.focus();
    }
  };

  const goToStep = (step: WizardStep) => {
    const targetIndex = steps.findIndex((s) => s.key === step);
    if (destinationLocked && targetIndex < detailsStepIndex) return;
    // Only allow going back to completed steps
    if (targetIndex <= currentStepIndex) {
      setCurrentStep(step);
      setErrors([]);
    }
  };

  // In an existing case the caption is read-only: it comes from the court's case record.
  const captionMissing = isMotionMode && !filingData.caseTitle.trim();
  const retryCaseLookup = () => {
    setCaseLookupError(null);
    setErrors([]);
    setReloadKey((key) => key + 1);
  };

  const getStepError = (): string => {
    if (plainLanguage) {
      switch (currentStep) {
        case 'court': return 'Choose the court where you want to file.';
        case 'case': return 'Pick an existing case or start a new one.';
        case 'case-type': return 'Select what kind of case this is.';
        case 'details': return captionMissing
          ? 'We could not load your case yet. Try again, or go Back and pick your case.'
          : 'Add a short title describing your filing.';
        case 'documents': return 'Upload at least one PDF or document.';
        default: return 'Finish this step to continue.';
      }
    }
    switch (currentStep) {
      case 'court': return 'Please select a court to continue.';
      case 'case': return 'Please choose an existing case or start a new case.';
      case 'case-type': return 'Please select a case type to continue.';
      case 'details': return captionMissing
        ? "The case title comes from the court's case record, which has not loaded. Retry loading it, or go Back to choose the case."
        : 'Please enter a case title to continue.';
      case 'documents': return 'Please upload at least one document to continue.';
      default: return 'Please complete this step to continue.';
    }
  };

  const handleDiscardDraft = () => {
    if (loadedFiling) {
      setFilingData(previous => ({ ...previous, caseTitle: loadedFiling.case_title ?? '',
        filingDescription: loadedFiling.filing_description ?? '', detailsToken: loadedFiling.details_token }));
      clearFilingDraft(draftKey, loadedFiling.id);
      setShowDraftBanner(false);
      setConflict(null);
      setErrors([]);
      return;
    }
    clearFilingDraft(draftKey, filingData.filingId ?? undefined);
    setLoadedFiling(null);
    setFilingData(defaultFilingData);
    setShowDraftBanner(false);
    setCurrentStep('court');
    setErrors([]);
    setSaving(false);
    setConflict(null);
    setSaveNotice('');
    setCreationConflictId(null);
  };

  useEffect(() => { conflictHeading.current?.focus(); }, [conflict]);

  const conflictView = conflict && <section className="review-card draft-conflict" aria-labelledby="draft-conflict-heading">
        <h3 id="draft-conflict-heading" ref={conflictHeading} tabIndex={-1}>Compare changes before saving</h3>
        <p>Your changes are still here. Compare them with the saved details before continuing.</p>
        <div className="draft-comparison">
          <div><h4>Your edits</h4><strong>{filingData.caseTitle || '(No title)'}</strong><p>{filingData.filingDescription || '(No description)'}</p></div>
          <div><h4>Saved to your account</h4><strong>{conflict.case_title || '(No title)'}</strong><p>{conflict.filing_description || '(No description)'}</p></div>
        </div>
        <div className="draft-actions">
          <button className="btn btn-secondary" onClick={() => resolveConflict(false)}>Use saved details</button>
          {['draft', 'returned'].includes(conflict.status)
            ? <button className="btn btn-primary" onClick={() => resolveConflict(true)}>Keep my edits for next save</button>
            : <Link to={`/filings/${conflict.id}/history`}>This filing is {conflict.status.replace('_', ' ')}. Open its history.</Link>}
        </div>
      </section>;

  if (loadingExisting) return <p className="loading" role="status">Loading filing...</p>;
  if (loadError) return <LoadError failure={loadError} onRetry={() => setReloadKey((key) => key + 1)} />;
  if (readOnly) {
    return (
      <div className="filing-wizard">
        <Link to="/filings">Back to My Filings</Link>
        <PageHeading>Filing #{loadedFiling.id}</PageHeading>
        {conflictView}
        <p>Status: <span className={`status-badge ${loadedFiling.status}`}>{loadedFiling.status.replace('_', ' ')}</span></p>
        {loadedFiling.rejection_reason && <p role="note">Clerk note: {loadedFiling.rejection_reason}</p>}
        <FilingReview filingId={loadedFiling.id} courtName={filingData.courtName} caseTypeName={filingData.caseTypeName} readOnly />
      </div>
    );
  }

  return (
    <div className="filing-wizard">
      <div className="wizard-header">
        <PageHeading>
          {loadedFiling ? `Continue Filing #${loadedFiling.id}` : isMotionMode
            ? plainLanguage
              ? 'File papers in an existing case'
              : 'File a Motion'
            : plainLanguage
              ? 'Start a new court filing'
              : 'New E-Filing'}
        </PageHeading>
        <div className="wizard-header-badges">
          <label className="srl-plain-toggle">
            <input
              type="checkbox"
              checked={plainLanguage}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                setPlainLanguage(e.target.checked);
                setPlainLanguageMode(e.target.checked);
              }}
            />
            Plain-language guidance
          </label>
          {isMotionMode && filingData.caseId && (
            <span className="motion-badge">Motion to Case #{filingData.caseId}</span>
          )}
          {filingData.filingId && (
            <span className="filing-id-badge">Filing #{filingData.filingId}</span>
          )}
        </div>
      </div>

      {/* Draft Recovery Banner */}
      {showDraftBanner && !conflict && (
        <div className="draft-banner">
          <span>Recovered unsaved edits from this tab. Save them to your account before closing the tab.</span>
          <div className="draft-actions">
            <button className="btn btn-primary btn-small" onClick={() => setShowDraftBanner(false)}>
              Continue Editing
            </button>
            <button className="btn btn-secondary btn-small" disabled={saving} onClick={handleDiscardDraft}>
              {loadedFiling ? 'Use Saved Details' : filingData.creationKey ? 'Start a separate filing' : 'Start Fresh'}
            </button>
          </div>
        </div>
      )}

      {saveNotice && <p className="alert alert-success" role="status">{saveNotice}</p>}
      {filingData.creationKey && !filingData.filingId && <p role="note">
        If the earlier save succeeded, retrying will reopen that filing.
      </p>}
      {dirty && !conflict && <p role="status">Unsaved changes. Use Save draft or Continue to save them to your account.</p>}
      {!recoveryAvailable && dirty && <p className="alert alert-warning" role="alert">
        This browser could not keep a recovery copy. Keep this page open and save your draft.
      </p>}
      {conflictView}
      {creationConflictId && <p className="alert alert-warning" role="alert">
        Your earlier save created filing #{creationConflictId}. Copy your edits before leaving this page,
        then <Link to={`/filing/new?filing_id=${creationConflictId}&step=details`}>open the saved filing</Link> to compare them.
      </p>}

      {loadedFiling?.status === 'returned' && loadedFiling.rejection_reason && !submission && (
        <div className="alert alert-warning" role="note">
          <strong>Returned for correction:</strong> {loadedFiling.rejection_reason}
        </div>
      )}

      {/* Step Progress Bar - clickable for completed steps */}
      <nav className="wizard-steps" aria-label="Filing progress">
        {steps.map((step, index) => (
          <button
            key={step.key}
            type="button"
            className={`wizard-step ${
              index === currentStepIndex
                ? 'active'
                : index < currentStepIndex
                ? 'completed'
                : 'upcoming'
            }`}
            onClick={() => goToStep(step.key)}
            disabled={Boolean(submission) || Boolean(conflict) || saving || index > currentStepIndex || (destinationLocked && index < detailsStepIndex)}
            aria-current={index === currentStepIndex ? 'step' : undefined}
          >
            <span className="step-number">
              {index < currentStepIndex ? '\u2713' : index + 1}
            </span>
            <span className="step-label">{step.label}</span>
          </button>
        ))}
      </nav>

      {/* Filing Summary Sidebar */}
      {filingData.courtId && currentStep !== 'review' && (
        <div className="filing-summary-bar">
          <span><strong>Court:</strong> {filingData.courtName}</span>
          {filingData.caseTypeName && (
            <span><strong>Type:</strong> {filingData.caseTypeName}</span>
          )}
          {filingData.caseTitle && (
            <span><strong>Case:</strong> {filingData.caseTitle}</span>
          )}
          <span><strong>Docs:</strong> {filingData.documents.length}</span>
        </div>
      )}

      {/* Validation Errors */}
      {errors.length > 0 && (
        <div className="alert alert-error" role="alert">
          {errors.map((e, i) => <p key={i}>{e}</p>)}
        </div>
      )}

      {/* Step Content */}
      <div className="wizard-content">
        {currentStep === 'court' && (
          <CourtSelector
            selectedCourtId={filingData.courtId}
            onSelect={(courtId, courtName) => {
              if (courtId === filingData.courtId) return;
              // Changing court invalidates any case picked in another court.
              updateData({
                courtId, courtName,
                caseTypeId: null, caseTypeName: '',
                caseId: null, caseTitle: '', caseChoiceMade: false, filingType: 'initial',
              });
            }}
          />
        )}

        {currentStep === 'case' && filingData.courtId && (
          <CaseSelector
            courtId={filingData.courtId}
            courtName={filingData.courtName}
            selectedCaseId={filingData.caseId}
            isNewChosen={filingData.caseChoiceMade && filingData.caseId === null}
            onChooseExisting={() => {
              if (filingData.caseId !== null) return;
              updateData({ caseChoiceMade: false, caseTypeId: null, caseTypeName: '', caseTitle: '' });
            }}
            onSelectExisting={(c: CaseResult, caseTypeName: string) => {
              updateData({
                caseId: c.id,
                caseTypeId: c.case_type_id,
                caseTypeName,
                caseTitle: c.title,
                filingType: 'subsequent',
                caseChoiceMade: true,
              });
            }}
            onSelectNew={() => {
              updateData({
                caseId: null,
                caseTitle: '',
                caseTypeId: null,
                caseTypeName: '',
                filingType: 'initial',
                caseChoiceMade: true,
              });
            }}
          />
        )}

        {currentStep === 'case-type' && filingData.courtId && (
          <CaseTypeSelector
            courtId={filingData.courtId}
            selectedCaseTypeId={filingData.caseTypeId}
            onSelect={(id, name) => {
              updateData({ caseTypeId: id, caseTypeName: name });
            }}
          />
        )}

        {currentStep === 'details' && (
          <div className="form-section">
            <h3>{isMotionMode ? 'Motion Details' : 'Case Details'}</h3>

            {captionMissing && caseLookupError && (
              <LoadError failure={{ ...caseLookupError, message: `${caseLookupError.message} Retry, or go Back to choose the case.` }}
                onRetry={retryCaseLookup} />
            )}

            {isMotionMode && filingData.caseTitle && (
              <div className="motion-case-info">
                <strong>Filing motion to:</strong> {filingData.caseTitle}
              </div>
            )}

            {/* Filing type selector - shown when filing to existing case */}
            {isMotionMode && (
              <fieldset className="form-group filing-type-fieldset">
                <legend>Filing Type <span className="required-marker">*</span></legend>
                <div className="filing-type-options">
                  <label className={`filing-type-option ${filingData.filingType === 'subsequent' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="filingType"
                      value="subsequent"
                      checked={filingData.filingType === 'subsequent'}
                      disabled={destinationLocked || saving}
                      onChange={() => updateData({ filingType: 'subsequent' })}
                    />
                    <div>
                      <strong>File with Court</strong>
                      <span>Document is filed with the court and reviewed by the clerk. Appears on the docket.</span>
                    </div>
                  </label>
                  <label className={`filing-type-option ${filingData.filingType === 'service_only' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="filingType"
                      value="service_only"
                      checked={filingData.filingType === 'service_only'}
                      disabled={destinationLocked || saving}
                      onChange={() => updateData({ filingType: 'service_only' })}
                    />
                    <div>
                      <strong>Service Only (No Court Filing)</strong>
                      <span>Record documents for service outside this app. No court filing, clerk review, or filing fee. This app does not deliver documents to other parties.</span>
                    </div>
                  </label>
                </div>
              </fieldset>
            )}

            <p className="info-text">
              {filingData.filingType === 'service_only'
                ? 'Describe the documents you are recording. You must arrange delivery to the other parties outside this app.'
                : isMotionMode
                ? 'Describe your motion. The case title is pre-filled from the existing case.'
                : <>Enter the case information. Fields marked with <span className="required-marker">*</span> are required.</>
              }
            </p>
            <div className="form-group">
              <label htmlFor="caseTitle">
                Case Title <span className="required-marker">*</span>
              </label>
              <input
                id="caseTitle"
                disabled={saving}
                type="text"
                value={filingData.caseTitle}
                onChange={(e) => updateData({ caseTitle: e.target.value })}
                placeholder="e.g., Smith v. Jones"
                aria-required="true"
                readOnly={isMotionMode}
                autoFocus={!isMotionMode}
              />
              {!isMotionMode && (
                <span className="field-hint">
                  Format: Plaintiff name v. Defendant name (e.g., &quot;Smith v. Jones&quot;)
                </span>
              )}
            </div>
            <div className="form-group">
              <label htmlFor="filingDesc">
                {filingData.filingType === 'service_only' ? 'Service Description' : isMotionMode ? 'Motion Description' : 'Filing Description'} <span className="required-marker">*</span>
              </label>
              <textarea
                id="filingDesc"
                disabled={saving}
                value={filingData.filingDescription}
                onChange={(e) => updateData({ filingDescription: e.target.value })}
                placeholder={filingData.filingType === 'service_only'
                  ? "e.g., Plaintiff's First Set of Interrogatories (MCR 2.309)"
                  : isMotionMode
                  ? "e.g., Motion for Summary Disposition under MCR 2.116(C)(10)"
                  : "Brief description of this filing (e.g., Initial complaint for breach of contract)..."
                }
                autoFocus={isMotionMode}
                rows={4}
              />
            </div>
          </div>
        )}

        {currentStep === 'documents' && filingData.filingId && (
          <DocumentUpload
            filingId={filingData.filingId}
            courtId={filingData.courtId!}
            caseTypeId={filingData.caseTypeId!}
            filingType={filingData.filingType}
            documents={filingData.documents}
            onDocumentsChange={(docs) => updateData({ documents: docs })}
            onBusyChange={setSaving}
          />
        )}

        {currentStep === 'review' && (
          <FilingReview
            filingId={filingData.filingId!}
            courtName={filingData.courtName}
            caseTypeName={filingData.caseTypeName}
            submission={submission}
            onFeesChange={handleFeesChange}
            onSubmittingChange={setSaving}
            onSubmitSuccess={(filing) => { clearFilingDraft(draftKey, filing.id); setSubmission(filing); }}
          />
        )}
      </div>

      {/* Navigation */}
      {!submission && (
        <div className="wizard-nav">
          <button
            className="btn btn-secondary"
            onClick={goBack}
            disabled={currentStepIndex === 0 || saving || (destinationLocked && currentStep === 'details')}
          >
            Back
          </button>
          <div className="wizard-nav-right">
            {currentStep === 'details' && <button className="btn btn-secondary"
              disabled={saving || Boolean(conflict) || !filingData.caseTitle.trim()}
              onClick={() => { void saveDetails(); }}>Save draft</button>}
            {currentStep !== 'review' && (
              <button
                className="btn btn-primary"
                onClick={goNext}
                disabled={saving || Boolean(conflict)}
              >
                {saving ? 'Saving...' : currentStepIndex === steps.length - 2 ? 'Review Filing' : 'Continue'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default FilingWizard;
