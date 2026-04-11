import { useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import CourtSelector from './CourtSelector';
import CaseTypeSelector from './CaseTypeSelector';
import DocumentUpload from './DocumentUpload';
import ServiceList from './ServiceList';
import PaymentForm from './PaymentForm';
import FilingReview from './FilingReview';
import { createFiling } from '../../api/filings';
import { getCourt } from '../../api/courts';

type WizardStep = 'court' | 'case-type' | 'details' | 'documents' | 'service' | 'payment' | 'review';

interface FilingData {
  courtId: number | null;
  courtName: string;
  caseId: number | null;  // existing case (for motions)
  filingType: 'initial' | 'subsequent' | 'service_only';
  caseTypeId: number | null;
  caseTypeName: string;
  filingFeeCents: number;
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
  serviceContacts: Array<{
    name: string;
    email: string;
    method: string;
  }>;
  paymentComplete: boolean;
  feeWaiverRequested: boolean;
  feeWaiverReason: string;
}

const STEPS: { key: WizardStep; label: string; required: boolean }[] = [
  { key: 'court', label: 'Select Court', required: true },
  { key: 'case-type', label: 'Case Type & Rules', required: true },
  { key: 'details', label: 'Case Details', required: true },
  { key: 'documents', label: 'Documents', required: true },
  { key: 'service', label: 'Service', required: false },
  { key: 'payment', label: 'Payment', required: true },
  { key: 'review', label: 'Review & Submit', required: true },
];

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
  filingFeeCents: 0,
  caseTitle: '',
  filingDescription: '',
  filingId: null,
  documents: [],
  serviceContacts: [],
  paymentComplete: false,
  feeWaiverRequested: false,
  feeWaiverReason: '',
};

function FilingWizard() {
  const [searchParams] = useSearchParams();
  const draft = loadDraft();
  const [currentStep, setCurrentStep] = useState<WizardStep>(draft ? 'court' : 'court');
  const [filingData, setFilingData] = useState<FilingData>(draft || defaultFilingData);
  const [showDraftBanner, setShowDraftBanner] = useState(!!draft);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [isMotionMode, setIsMotionMode] = useState(false);

  // Pre-fill from URL params (e.g., "File a Motion" from case detail page)
  useEffect(() => {
    const caseId = searchParams.get('case_id');
    const courtId = searchParams.get('court_id');
    const caseTypeId = searchParams.get('case_type_id');
    const caseTitle = searchParams.get('case_title');

    const serviceOnly = searchParams.get('service_only') === 'true';

    if (caseId && courtId && caseTypeId) {
      clearDraft();
      setIsMotionMode(true);
      const numCourtId = Number(courtId);
      setFilingData({
        ...defaultFilingData,
        caseId: Number(caseId),
        courtId: numCourtId,
        courtName: '',
        filingType: serviceOnly ? 'service_only' : 'subsequent',
        caseTypeId: Number(caseTypeId),
        caseTypeName: '',
        caseTitle: caseTitle || '',
        filingDescription: '',
        paymentComplete: serviceOnly,
      });
      setCurrentStep('details');
      setShowDraftBanner(false);
      // Fetch actual court name
      getCourt(numCourtId).then(court => {
        setFilingData(prev => ({ ...prev, courtName: court.name }));
      }).catch(() => {
        setFilingData(prev => ({ ...prev, courtName: `Court #${courtId}` }));
      });
    }
  }, [searchParams]);

  const currentStepIndex = STEPS.findIndex((s) => s.key === currentStep);

  const updateData = useCallback((updates: Partial<FilingData>) => {
    setFilingData((prev) => {
      const next = { ...prev, ...updates };
      saveDraft(next);
      return next;
    });
  }, []);

  const canProceed = (): boolean => {
    switch (currentStep) {
      case 'court':
        return filingData.courtId !== null;
      case 'case-type':
        return filingData.caseTypeId !== null;
      case 'details':
        return filingData.caseTitle.trim().length > 0;
      case 'documents':
        return filingData.documents.length > 0;
      case 'service':
        return true; // optional
      case 'payment':
        return filingData.paymentComplete || filingData.filingFeeCents === 0 || filingData.filingType === 'service_only';
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

    // Create the filing envelope on the server when moving past details
    if (currentStep === 'details' && !filingData.filingId) {
      setSaving(true);
      try {
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
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Unknown error';
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        const detail = axiosErr?.response?.data?.detail;
        setErrors([`Failed to create filing: ${detail || msg}`]);
        setSaving(false);
        return;
      }
      setSaving(false);
    }

    if (currentStepIndex < STEPS.length - 1) {
      setCurrentStep(STEPS[currentStepIndex + 1].key);
      window.scrollTo(0, 0);
    }
  };

  const goBack = () => {
    setErrors([]);
    if (currentStepIndex > 0) {
      setCurrentStep(STEPS[currentStepIndex - 1].key);
      window.scrollTo(0, 0);
    }
  };

  const goToStep = (step: WizardStep) => {
    const targetIndex = STEPS.findIndex((s) => s.key === step);
    // Only allow going back to completed steps
    if (targetIndex <= currentStepIndex) {
      setCurrentStep(step);
      setErrors([]);
    }
  };

  const getStepError = (): string => {
    switch (currentStep) {
      case 'court': return 'Please select a court to continue.';
      case 'case-type': return 'Please select a case type to continue.';
      case 'details': return 'Please enter a case title to continue.';
      case 'documents': return 'Please upload at least one document to continue.';
      case 'payment': return 'Please complete payment to continue.';
      default: return 'Please complete this step to continue.';
    }
  };

  const handleDiscardDraft = () => {
    clearDraft();
    setFilingData(defaultFilingData);
    setShowDraftBanner(false);
    setCurrentStep('court');
    setErrors([]);
    setSaving(false);
    setIsMotionMode(false);
  };

  const formatFee = (cents: number) => cents === 0 ? 'No fee' : `$${(cents / 100).toFixed(2)}`;

  return (
    <div className="filing-wizard">
      <div className="wizard-header">
        <h2>{isMotionMode ? 'File a Motion' : 'New E-Filing'}</h2>
        <div className="wizard-header-badges">
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
        {STEPS.map((step, index) => (
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
            disabled={index > currentStepIndex}
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
          {filingData.caseTitle && (
            <span><strong>Case:</strong> {filingData.caseTitle}</span>
          )}
          {filingData.filingFeeCents > 0 && (
            <span><strong>Fee:</strong> {formatFee(filingData.filingFeeCents)}</span>
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
              updateData({ courtId, courtName, caseTypeId: null, caseTypeName: '' });
            }}
          />
        )}

        {currentStep === 'case-type' && filingData.courtId && (
          <CaseTypeSelector
            courtId={filingData.courtId}
            selectedCaseTypeId={filingData.caseTypeId}
            onSelect={(id, name, feeCents) => {
              updateData({ caseTypeId: id, caseTypeName: name, filingFeeCents: feeCents });
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
                      onChange={() => updateData({ filingType: 'service_only', paymentComplete: true })}
                    />
                    <div>
                      <strong>Service Only (No Court Filing)</strong>
                      <span>Document is served on other parties only. Not filed with the court, no clerk review, no filing fee. Common for discovery requests, interrogatories, and other party-to-party documents.</span>
                    </div>
                  </label>
                </div>
              </div>
            )}

            <p className="info-text">
              {filingData.filingType === 'service_only'
                ? 'Describe the documents you are serving. These will be delivered to the service contacts but not filed with the court.'
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
                  Format: Plaintiff name v. Defendant name (e.g., "Smith v. Jones")
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
          />
        )}

        {currentStep === 'documents' && !filingData.filingId && (
          <div className="form-section">
            <h3>Upload Documents</h3>
            <div className="alert alert-info">
              Your filing will be created when you proceed. You can then upload documents.
            </div>
          </div>
        )}

        {currentStep === 'service' && (
          <ServiceList
            contacts={filingData.serviceContacts}
            onChange={(contacts) => updateData({ serviceContacts: contacts })}
          />
        )}

        {currentStep === 'payment' && filingData.courtId && filingData.caseTypeId && (
          <PaymentForm
            courtId={filingData.courtId}
            caseTypeId={filingData.caseTypeId}
            filingId={filingData.filingId}
            onPaymentComplete={() => updateData({ paymentComplete: true })}
          />
        )}

        {currentStep === 'review' && (
          <FilingReview
            filingData={filingData}
            filingId={filingData.filingId}
            onSubmitSuccess={clearDraft}
          />
        )}
      </div>

      {/* Navigation */}
      <div className="wizard-nav">
        <button
          className="btn btn-secondary"
          onClick={goBack}
          disabled={currentStepIndex === 0}
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
              {saving ? 'Saving...' : currentStepIndex === STEPS.length - 2 ? 'Review Filing' : 'Continue'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default FilingWizard;
