const STORAGE_KEY = 'muefs_srl_plain_language';

export function isPlainLanguageMode(): boolean {
  return localStorage.getItem(STORAGE_KEY) === 'true';
}

export function hasPlainLanguagePreference(): boolean {
  return localStorage.getItem(STORAGE_KEY) !== null;
}

export function setPlainLanguageMode(on: boolean): void {
  localStorage.setItem(STORAGE_KEY, on ? 'true' : 'false');
}

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
