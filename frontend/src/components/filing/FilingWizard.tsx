import { useState, useCallback } from 'react';
import CourtSelector from './CourtSelector';
import CaseTypeSelector from './CaseTypeSelector';
import DocumentUpload from './DocumentUpload';
import ServiceList from './ServiceList';
import PaymentForm from './PaymentForm';
import FilingReview from './FilingReview';
import { createFiling, FilingEnvelope } from '../../api/filings';

type WizardStep = 'court' | 'case-type' | 'details' | 'documents' | 'service' | 'payment' | 'review';

interface FilingData {
  courtId: number | null;
  courtName: string;
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
  caseTypeId: null,
  caseTypeName: '',
  filingFeeCents: 0,
  caseTitle: '',
  filingDescription: '',
  filingId: null,
  documents: [],
  serviceContacts: [],
  paymentComplete: false,
};

function FilingWizard() {
  const draft = loadDraft();
  const [currentStep, setCurrentStep] = useState<WizardStep>(draft ? 'court' : 'court');
  const [filingData, setFilingData] = useState<FilingData>(draft || defaultFilingData);
  const [showDraftBanner, setShowDraftBanner] = useState(!!draft);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

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
        return filingData.paymentComplete || filingData.filingFeeCents === 0;
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
          case_type_id: filingData.caseTypeId!,
          case_title: filingData.caseTitle,
          filing_description: filingData.filingDescription,
        });
        updateData({ filingId: envelope.id });
      } catch {
        setErrors(['Failed to create filing. Please try again.']);
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
  };

  const formatFee = (cents: number) => cents === 0 ? 'No fee' : `$${(cents / 100).toFixed(2)}`;

  return (
    <div className="filing-wizard">
      <div className="wizard-header">
        <h2>New E-Filing</h2>
        {filingData.filingId && (
          <span className="filing-id-badge">Filing #{filingData.filingId}</span>
        )}
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
            <h3>Case Details</h3>
            <p className="info-text">
              Enter the case information. Fields marked with <span className="required-marker">*</span> are required.
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
                autoFocus
              />
              <span className="field-hint">
                Format: Plaintiff name v. Defendant name (e.g., "Smith v. Jones")
              </span>
            </div>
            <div className="form-group">
              <label htmlFor="filingDesc">Filing Description</label>
              <textarea
                id="filingDesc"
                value={filingData.filingDescription}
                onChange={(e) => updateData({ filingDescription: e.target.value })}
                placeholder="Brief description of this filing (e.g., Initial complaint for breach of contract)..."
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
