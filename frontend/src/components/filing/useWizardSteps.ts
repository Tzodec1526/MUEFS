import { useState } from 'react';
import type { FilingDraft } from '../../utils/filingDraft';
import { plainStepLabel } from '../../utils/srlMode';
import type { FilingData } from './useFilingDraft';

export type WizardStep = 'court' | 'case' | 'case-type' | 'details' | 'documents' | 'review';

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

const STEP_ERRORS: Record<WizardStep, { plain: string; standard: string }> = {
  court: { plain: 'Choose the court where you want to file.', standard: 'Please select a court to continue.' },
  case: { plain: 'Pick an existing case or start a new one.', standard: 'Please choose an existing case or start a new case.' },
  'case-type': { plain: 'Select what kind of case this is.', standard: 'Please select a case type to continue.' },
  details: { plain: 'Add a short title describing your filing.', standard: 'Please enter a case title to continue.' },
  documents: { plain: 'Upload at least one PDF or document.', standard: 'Please upload at least one document to continue.' },
  review: { plain: 'Finish this step to continue.', standard: 'Please complete this step to continue.' },
};

const CAPTION_MISSING_ERROR = {
  plain: 'We could not load your case yet. Try again, or go Back and pick your case.',
  standard: "The case title comes from the court's case record, which has not loaded. Retry loading it, or go Back to choose the case.",
};

export function useWizardSteps({ draft, filingData, plainLanguage, destinationLocked, captionMissing, saveDetails }: {
  draft: FilingDraft | null;
  filingData: FilingData;
  plainLanguage: boolean;
  destinationLocked: boolean;
  captionMissing: boolean;
  saveDetails: (advance: boolean) => Promise<boolean>;
}) {
  const [currentStep, setCurrentStep] = useState<WizardStep>(() =>
    draft?.creationKey ? 'details' : draft ? 'court' : filingData.caseId ? 'details' : filingData.courtId ? 'case' : 'court'
  );
  const [errors, setErrors] = useState<string[]>([]);
  const steps = buildSteps(filingData.filingType).map((s) => ({
    ...s,
    label: plainLanguage ? plainStepLabel(s.key, s.label) : s.label,
  }));
  const currentStepIndex = steps.findIndex((s) => s.key === currentStep);
  const detailsStepIndex = steps.findIndex((s) => s.key === 'details');

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

  const getStepError = (): string => {
    const messages = currentStep === 'details' && captionMissing ? CAPTION_MISSING_ERROR : STEP_ERRORS[currentStep];
    return plainLanguage ? messages.plain : messages.standard;
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
    if (targetIndex <= currentStepIndex) {
      setCurrentStep(step);
      setErrors([]);
    }
  };

  return {
    currentStep, setCurrentStep, errors, setErrors, steps, currentStepIndex, detailsStepIndex, goNext, goBack, goToStep,
  };
}
