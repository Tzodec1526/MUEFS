import { useState } from 'react';
import CourtSelector from './CourtSelector';
import CaseTypeSelector from './CaseTypeSelector';
import DocumentUpload from './DocumentUpload';
import ServiceList from './ServiceList';
import FilingReview from './FilingReview';

type WizardStep = 'court' | 'case-type' | 'details' | 'documents' | 'service' | 'review';

interface FilingData {
  courtId: number | null;
  courtName: string;
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
  }>;
  serviceContacts: Array<{
    name: string;
    email: string;
    method: string;
  }>;
}

const STEPS: { key: WizardStep; label: string }[] = [
  { key: 'court', label: '1. Select Court' },
  { key: 'case-type', label: '2. Case Type' },
  { key: 'details', label: '3. Case Details' },
  { key: 'documents', label: '4. Documents' },
  { key: 'service', label: '5. Service List' },
  { key: 'review', label: '6. Review & Submit' },
];

function FilingWizard() {
  const [currentStep, setCurrentStep] = useState<WizardStep>('court');
  const [filingData, setFilingData] = useState<FilingData>({
    courtId: null,
    courtName: '',
    caseTypeId: null,
    caseTypeName: '',
    caseTitle: '',
    filingDescription: '',
    filingId: null,
    documents: [],
    serviceContacts: [],
  });

  const currentStepIndex = STEPS.findIndex((s) => s.key === currentStep);

  const goNext = () => {
    if (currentStepIndex < STEPS.length - 1) {
      setCurrentStep(STEPS[currentStepIndex + 1].key);
    }
  };

  const goBack = () => {
    if (currentStepIndex > 0) {
      setCurrentStep(STEPS[currentStepIndex - 1].key);
    }
  };

  return (
    <div className="filing-wizard">
      <h2>New E-Filing</h2>

      {/* Step Progress Bar */}
      <div className="wizard-steps">
        {STEPS.map((step, index) => (
          <div
            key={step.key}
            className={`wizard-step ${
              index === currentStepIndex
                ? 'active'
                : index < currentStepIndex
                ? 'completed'
                : ''
            }`}
          >
            <span className="step-number">{index + 1}</span>
            <span className="step-label">{step.label.split('. ')[1]}</span>
          </div>
        ))}
      </div>

      {/* Step Content */}
      <div className="wizard-content">
        {currentStep === 'court' && (
          <CourtSelector
            selectedCourtId={filingData.courtId}
            onSelect={(courtId, courtName) => {
              setFilingData({ ...filingData, courtId, courtName });
            }}
          />
        )}

        {currentStep === 'case-type' && filingData.courtId && (
          <CaseTypeSelector
            courtId={filingData.courtId}
            selectedCaseTypeId={filingData.caseTypeId}
            onSelect={(id, name) => {
              setFilingData({ ...filingData, caseTypeId: id, caseTypeName: name });
            }}
          />
        )}

        {currentStep === 'details' && (
          <div className="form-section">
            <h3>Case Details</h3>
            <div className="form-group">
              <label htmlFor="caseTitle">Case Title</label>
              <input
                id="caseTitle"
                type="text"
                value={filingData.caseTitle}
                onChange={(e) =>
                  setFilingData({ ...filingData, caseTitle: e.target.value })
                }
                placeholder="e.g., Smith v. Jones"
              />
            </div>
            <div className="form-group">
              <label htmlFor="filingDesc">Filing Description</label>
              <textarea
                id="filingDesc"
                value={filingData.filingDescription}
                onChange={(e) =>
                  setFilingData({
                    ...filingData,
                    filingDescription: e.target.value,
                  })
                }
                placeholder="Brief description of this filing..."
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
            onDocumentsChange={(docs) =>
              setFilingData({ ...filingData, documents: docs })
            }
          />
        )}

        {currentStep === 'documents' && !filingData.filingId && (
          <div className="form-section">
            <h3>Upload Documents</h3>
            <p className="info-text">
              Filing will be created when you proceed. You can then upload documents.
            </p>
          </div>
        )}

        {currentStep === 'service' && (
          <ServiceList
            contacts={filingData.serviceContacts}
            onChange={(contacts) =>
              setFilingData({ ...filingData, serviceContacts: contacts })
            }
          />
        )}

        {currentStep === 'review' && (
          <FilingReview
            filingData={filingData}
            filingId={filingData.filingId}
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
        <button
          className="btn btn-primary"
          onClick={goNext}
          disabled={currentStepIndex === STEPS.length - 1}
        >
          {currentStepIndex === STEPS.length - 2 ? 'Review Filing' : 'Next'}
        </button>
      </div>
    </div>
  );
}

export default FilingWizard;
