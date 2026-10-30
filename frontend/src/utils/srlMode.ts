const STORAGE_KEY = 'muefs_srl_plain_language';

export function isPlainLanguageMode(): boolean {
  return localStorage.getItem(STORAGE_KEY) === 'true';
}

/** Whether the filer has chosen either way; an explicit opt-out must not be reset to a default. */
export function hasPlainLanguagePreference(): boolean {
  return localStorage.getItem(STORAGE_KEY) !== null;
}

export function setPlainLanguageMode(on: boolean): void {
  localStorage.setItem(STORAGE_KEY, on ? 'true' : 'false');
}

/** Step labels in plain language for self-represented litigants. */
const PLAIN_STEP_LABELS: Record<string, string> = {
  court: 'Your court',
  case: 'Your case',
  'case-type': 'Kind of case',
  details: 'Your filing',
  documents: 'Your papers',
  review: 'Check and send',
};

export function plainStepLabel(key: string, defaultLabel: string): string {
  return PLAIN_STEP_LABELS[key] || defaultLabel;
}
