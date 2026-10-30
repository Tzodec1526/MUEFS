interface WizardStepperProps<Key extends string> {
  steps: { key: Key; label: string }[];
  currentIndex: number;
  locked: boolean;
  earliestIndex: number;
  onSelect: (key: Key) => void;
}

function WizardStepper<Key extends string>({ steps, currentIndex, locked, earliestIndex, onSelect }: WizardStepperProps<Key>) {
  return (
    <nav className="wizard-steps" aria-label="Filing progress">
      {steps.map((step, index) => (
        <button
          key={step.key}
          type="button"
          className={`wizard-step ${
            index === currentIndex
              ? 'active'
              : index < currentIndex
              ? 'completed'
              : 'upcoming'
          }`}
          onClick={() => onSelect(step.key)}
          disabled={locked || index > currentIndex || index < earliestIndex}
          aria-current={index === currentIndex ? 'step' : undefined}
        >
          <span className="step-number">
            {index < currentIndex ? '✓' : index + 1}
          </span>
          <span className="step-label">{step.label}</span>
        </button>
      ))}
    </nav>
  );
}

export default WizardStepper;
