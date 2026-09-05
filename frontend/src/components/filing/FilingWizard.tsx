import { useState, useEffect, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import CourtSelector from './CourtSelector';
import CaseSelector, { CaseResult } from './CaseSelector';
import CaseTypeSelector from './CaseTypeSelector';
import DocumentUpload from './DocumentUpload';
import FilingReview from './FilingReview';
import { getErrorDetail } from '../../utils/errors';
import { createFiling, getFiling, updateFiling, type FilingEnvelope } from '../../api/filings';
import LoadError from '../common/LoadError';
import { getCourt, getCaseTypes, getFilingChecklists, FilingChecklist } from '../../api/courts';
import { getDemoRole } from '../auth/LoginScreen';
import {
  isPlainLanguageMode,
  setPlainLanguageMode,
  stepLabel,
} from '../../utils/srlMode';

type WizardStep = 'court' | 'case' | 'case-type' | 'details' | 'documents' | 'review';

interface FilingData {
  courtId: number | null;
  courtName: string;
  caseId: number | null;  // existing case (for motions)
  filingType: 'initial' | 'subsequent' | 'service_only';
  caseTypeId: number | null;
  caseTypeName: string;
  caseTitle: string;
  filingDescription: string;
  filingId: number | null;
  documents: Array<{
    id: number;
    title: string;
    type: string;
    size: number;
    isSearchable: boolean;
  }>;
  paymentComplete: boolean;
  caseChoiceMade: boolean;  // user picked existing-case or new-case on the 'case' step
  feeWaiverRequested: boolean;
  feeWaiverReason: string;
  motionSubtype: string | null;  // selected motion type for subsequent civil filings
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

const AUTOSAVE_KEY = 'muefs_filing_draft';

function loadDraft(): FilingData | null {
  try {
    const saved = localStorage.getItem(AUTOSAVE_KEY);
    if (saved) return JSON.parse(saved);
  } catch { /* ignore */ }
  return null;
}

function saveDraft(data: FilingData) {
  try {
    localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(data));
  } catch { /* ignore */ }
}

function clearDraft() {
  localStorage.removeItem(AUTOSAVE_KEY);
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
  documents: [],
  paymentComplete: false,
  caseChoiceMade: false,
  feeWaiverRequested: false,
  feeWaiverReason: '',
  motionSubtype: null,
};

function FilingWizard() {
  const [searchParams] = useSearchParams();
  const [draft] = useState(() => searchParams.size ? null : loadDraft());
  const requestedFilingId = searchParams.get('filing_id') || (draft?.filingId ? String(draft.filingId) : null);
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
      caseTitle: searchParams.get('case_title') || '',
      filingType: serviceOnly ? 'service_only' : 'subsequent',
      caseChoiceMade: true,
    };
  });
  const [currentStep, setCurrentStep] = useState<WizardStep>(() =>
    draft ? 'court' : filingData.caseId ? 'details' : filingData.courtId ? 'case' : 'court'
  );
  const [showDraftBanner, setShowDraftBanner] = useState(!!draft);
  const [saving, setSaving] = useState(false);
  const [loadedFiling, setLoadedFiling] = useState<FilingEnvelope | null>(null);
  const readOnly = loadedFiling !== null && !['draft', 'returned'].includes(loadedFiling.status);
  const [loadingExisting, setLoadingExisting] = useState(Boolean(requestedFilingId));
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [submission, setSubmission] = useState<FilingEnvelope>();
  const [errors, setErrors] = useState<string[]>([]);
  const handlePaymentComplete = useCallback(() => {
    setFilingData(prev => ({ ...prev, paymentComplete: true }));
  }, []);
  const isMotionMode = filingData.filingType !== 'initial';
  const [motionChecklists, setMotionChecklists] = useState<FilingChecklist[]>([]);
  const [plainLanguage, setPlainLanguage] = useState(() => {
    if (getDemoRole() === 'srl') {
      if (!isPlainLanguageMode()) setPlainLanguageMode(true);
      return true;
    }
    return isPlainLanguageMode();
  });

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
            getCaseTypes(envelope.court_id),
          ]);
          if (controller.signal.aborted) return;
          const caseType = types.find((type) => type.id === envelope.case_type_id);
          const filingType = envelope.filing_type === 'initial' || envelope.filing_type === 'service_only'
            ? envelope.filing_type : 'subsequent';
          const recoveredDraft = draft?.filingId === envelope.id
            && ['draft', 'returned'].includes(envelope.status) ? draft : null;
          if (draft?.filingId === envelope.id && !recoveredDraft) clearDraft();
          setLoadedFiling(envelope);
          setFilingData({
            ...defaultFilingData,
            filingId: envelope.id,
            courtId: envelope.court_id,
            courtName: court.name,
            caseId: envelope.case_id,
            caseTypeId: envelope.case_type_id,
            caseTypeName: caseType?.name || '',
            filingType,
            caseTitle: recoveredDraft?.caseTitle ?? envelope.case_title ?? '',
            filingDescription: recoveredDraft?.filingDescription ?? envelope.filing_description ?? '',
            motionSubtype: recoveredDraft?.motionSubtype ?? null,
            caseChoiceMade: true,
            paymentComplete: envelope.payment_id != null || envelope.fee_waiver_requested
              || envelope.fee_waiver_granted === true,
            feeWaiverRequested: envelope.fee_waiver_requested,
            feeWaiverReason: envelope.fee_waiver_reason || '',
            documents: envelope.documents.map((doc) => ({
              id: doc.id, title: doc.title, type: doc.document_type_code,
              size: doc.file_size_bytes, isSearchable: doc.is_text_searchable,
            })),
          });
          setCurrentStep('documents');
          setShowDraftBanner(recoveredDraft !== null);
        } catch (err) {
          if (!controller.signal.aborted) {
            setLoadError(getErrorDetail(err) || 'Could not load this filing. Please retry.');
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
    let active = true;
    Promise.all([
      getCourt(Number(courtId)).catch(() => ({ name: `Court #${courtId}` })),
      caseTypeId ? getCaseTypes(Number(courtId)).catch(() => []) : Promise.resolve([]),
    ]).then(([court, types]) => {
      if (active) setFilingData(prev => prev.courtId !== Number(courtId) ? prev : {
        ...prev,
        courtName: court.name,
        caseTypeName: types.find(t => t.id === prev.caseTypeId)?.name || prev.caseTypeName,
      });
    });
    return () => { active = false; };
  }, [searchParams, requestedFilingId, draft, reloadKey]);

  // Fetch motion checklists dynamically when in motion mode (for subtype dropdown + pre-fill).
  // Focused on civil cases per requirements (civil case types will surface relevant motion checklists like Summary Disposition, General Motion, etc.)
  useEffect(() => {
    if (!isMotionMode || readOnly || !filingData.courtId || !filingData.caseTypeId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional reset when leaving motion mode
      setMotionChecklists([]);
      return;
    }
    async function fetchChecklists() {
      try {
        const lists = await getFilingChecklists(filingData.courtId!, filingData.caseTypeId!);
        // Prioritize civil-focused motion types for this feature
        const civilLists = lists.filter((l) =>
          /civil|summary disposition|general motion|discovery|default|reconsider|in limine|injunction/i.test(l.motion_type)
        );
        setMotionChecklists(civilLists.length > 0 ? civilLists : lists);
      } catch {
        setMotionChecklists([]);
      }
    }
    fetchChecklists();
  }, [isMotionMode, readOnly, filingData.courtId, filingData.caseTypeId]);

  const steps = buildSteps(filingData.filingType).map((s) => ({
    ...s,
    label: plainLanguage ? stepLabel(s.key, s.label) : s.label,
  }));
  const currentStepIndex = steps.findIndex((s) => s.key === currentStep);
  const detailsStepIndex = steps.findIndex((s) => s.key === 'details');

  const updateData = (updates: Partial<FilingData>) => {
    setFilingData((prev) => ({ ...prev, ...updates }));
  };

  useEffect(() => {
    if (filingData.courtId && !loadingExisting && !loadError && !readOnly && !submission) {
      saveDraft(filingData);
    }
  }, [filingData, loadingExisting, loadError, readOnly, submission]);

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

    // Persist edits as well as new envelopes before moving to documents.
    if (currentStep === 'details') {
      setSaving(true);
      try {
        if (filingData.filingId) {
          await updateFiling(filingData.filingId, {
            case_title: filingData.caseTitle,
            filing_description: filingData.filingDescription,
          });
        } else {
          const envelope = await createFiling({
            court_id: filingData.courtId!,
            case_id: filingData.caseId || undefined,
            case_type_id: filingData.caseTypeId!,
            filing_type: filingData.filingType,
            case_title: filingData.caseTitle,
            filing_description: filingData.filingDescription,
            fee_waiver_requested: filingData.feeWaiverRequested,
            fee_waiver_reason: filingData.feeWaiverReason || undefined,
          });
          updateData({ filingId: envelope.id });
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Unknown error';
        const detail = getErrorDetail(err);
        setErrors([`Failed to save filing: ${detail || msg}`]);
        setSaving(false);
        return;
      }
      setSaving(false);
    }

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
    if (filingData.filingId && targetIndex < detailsStepIndex) return;
    // Only allow going back to completed steps
    if (targetIndex <= currentStepIndex) {
      setCurrentStep(step);
      setErrors([]);
    }
  };

  const getStepError = (): string => {
    if (plainLanguage) {
      switch (currentStep) {
        case 'court': return 'Choose the court where you want to file.';
        case 'case': return 'Pick an existing case or start a new one.';
        case 'case-type': return 'Select what kind of case this is.';
        case 'details': return 'Add a short title describing your filing.';
        case 'documents': return 'Upload at least one PDF or document.';
        default: return 'Finish this step to continue.';
      }
    }
    switch (currentStep) {
      case 'court': return 'Please select a court to continue.';
      case 'case': return 'Please choose an existing case or start a new case.';
      case 'case-type': return 'Please select a case type to continue.';
      case 'details': return 'Please enter a case title to continue.';
      case 'documents': return 'Please upload at least one document to continue.';
      default: return 'Please complete this step to continue.';
    }
  };

  const handleDiscardDraft = () => {
    clearDraft();
    setLoadedFiling(null);
    setFilingData(defaultFilingData);
    setShowDraftBanner(false);
    setCurrentStep('court');
    setErrors([]);
    setSaving(false);
    setMotionChecklists([]);
  };

  if (loadingExisting) return <p className="loading" role="status">Loading filing...</p>;
  if (loadError) return <LoadError message={loadError} onRetry={() => setReloadKey((key) => key + 1)} />;
  if (readOnly) {
    return (
      <div className="filing-wizard">
        <Link to="/filings">Back to My Filings</Link>
        <h2>Filing #{loadedFiling.id}</h2>
        <p>Status: <span className={`status-badge ${loadedFiling.status}`}>{loadedFiling.status.replace('_', ' ')}</span></p>
        {loadedFiling.rejection_reason && <p role="note">Clerk note: {loadedFiling.rejection_reason}</p>}
        <FilingReview filingData={filingData} readOnly />
      </div>
    );
  }

  return (
    <div className="filing-wizard">
      <div className="wizard-header">
        <h2>
          {loadedFiling ? `Continue Filing #${loadedFiling.id}` : isMotionMode
            ? plainLanguage
              ? 'File papers in an existing case'
              : 'File a Motion'
            : plainLanguage
              ? 'Start a new court filing'
              : 'New E-Filing'}
        </h2>
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
      {showDraftBanner && (
        <div className="draft-banner">
          <span>You have an unsaved draft filing. Would you like to continue?</span>
          <div className="draft-actions">
            <button className="btn btn-primary btn-small" onClick={() => setShowDraftBanner(false)}>
              Continue Draft
            </button>
            <button className="btn btn-secondary btn-small" onClick={handleDiscardDraft}>
              Start Fresh
            </button>
          </div>
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
            disabled={Boolean(submission) || index > currentStepIndex || Boolean(filingData.filingId && index < detailsStepIndex)}
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
      {filingData.courtId && (
        <div className="filing-summary-bar">
          <span><strong>Court:</strong> {filingData.courtName}</span>
          {filingData.caseTypeName && (
            <span><strong>Type:</strong> {filingData.caseTypeName}</span>
          )}
          {filingData.motionSubtype && (
            <span><strong>Motion:</strong> {filingData.motionSubtype}</span>
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
            onSelectExisting={(c: CaseResult, caseTypeName: string) => {
              updateData({
                caseId: c.id,
                caseTypeId: c.case_type_id,
                caseTypeName,
                caseTitle: c.title,
                filingType: 'subsequent',
                caseChoiceMade: true,
                motionSubtype: null,
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
              updateData({ caseTypeId: id, caseTypeName: name, motionSubtype: null });
            }}
          />
        )}

        {currentStep === 'details' && (
          <div className="form-section">
            <h3>{isMotionMode ? 'Motion Details' : 'Case Details'}</h3>

            {isMotionMode && filingData.caseTitle && (
              <div className="motion-case-info">
                <strong>Filing motion to:</strong> {filingData.caseTitle}
              </div>
            )}

            {/* Filing type selector - shown when filing to existing case */}
            {isMotionMode && (
              <div className="form-group">
                <label htmlFor="filingType">Filing Type <span className="required-marker">*</span></label>
                <div className="filing-type-options">
                  <label className={`filing-type-option ${filingData.filingType === 'subsequent' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="filingType"
                      value="subsequent"
                      checked={filingData.filingType === 'subsequent'}
                      disabled={filingData.filingId !== null}
                      onChange={() => updateData({ filingType: 'subsequent', paymentComplete: false })}
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
                      disabled={filingData.filingId !== null}
                      onChange={() => updateData({ filingType: 'service_only' })}
                    />
                    <div>
                      <strong>Service Only (No Court Filing)</strong>
                      <span>Record documents for service outside this app. No court filing, clerk review, or filing fee. This app does not deliver documents to other parties.</span>
                    </div>
                  </label>
                </div>
              </div>
            )}

            {/* Motion Subtype Dropdown - added for civil cases. Populated dynamically from backend checklists (MCR 2.116, 2.119, 2.313 etc.) */}
            {isMotionMode && motionChecklists.length > 0 && (
              <div className="form-group">
                <label htmlFor="motionSubtype">
                  Motion Subtype (Civil, optional)
                </label>
                <select
                  id="motionSubtype"
                  value={filingData.motionSubtype || ''}
                  onChange={(e) => updateData({ motionSubtype: e.target.value || null })}
                >
                  <option value="">-- Select specific motion type --</option>
                  {motionChecklists.map((cl) => (
                    <option key={cl.id} value={cl.motion_type}>
                      {cl.motion_type}
                    </option>
                  ))}
                </select>
                {filingData.motionSubtype && (
                  <span className="field-hint">
                    {motionChecklists.find((c) => c.motion_type === filingData.motionSubtype)?.help_text || 'Select to pre-fill required companion documents below.'}
                  </span>
                )}
              </div>
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
            documents={filingData.documents}
            onDocumentsChange={(docs) => updateData({ documents: docs })}
            motionSubtype={filingData.motionSubtype}
          />
        )}

        {currentStep === 'review' && (
          <FilingReview
            filingData={filingData}
            submission={submission}
            onPaymentComplete={handlePaymentComplete}
            onSubmitSuccess={(filing) => { clearDraft(); setSubmission(filing); }}
          />
        )}
      </div>

      {/* Navigation */}
      {!submission && (
        <div className="wizard-nav">
          <button
            className="btn btn-secondary"
            onClick={goBack}
            disabled={currentStepIndex === 0 || saving || Boolean(filingData.filingId && currentStep === 'details')}
          >
            Back
          </button>
          <div className="wizard-nav-right">
            {currentStep !== 'review' && (
              <button
                className="btn btn-primary"
                onClick={goNext}
                disabled={saving}
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
