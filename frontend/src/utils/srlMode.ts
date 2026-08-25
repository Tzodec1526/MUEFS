const STORAGE_KEY = 'muefs_srl_plain_language';

export function isPlainLanguageMode(): boolean {
  return localStorage.getItem(STORAGE_KEY) === 'true';
}

export function setPlainLanguageMode(on: boolean): void {
  localStorage.setItem(STORAGE_KEY, on ? 'true' : 'false');
}

/** Step labels in plain language for self-represented litigants. */
export const PLAIN_STEP_LABELS: Record<string, string> = {
  court: 'Pick your court',
  case: 'Your case',
  'case-type': 'What kind of case',
  details: 'Tell us about your filing',
  documents: 'Upload your papers',
  service: 'Who to notify',
  review: 'Check and send',
};

export function stepLabel(key: string, defaultLabel: string): string {
  if (!isPlainLanguageMode()) return defaultLabel;
  return PLAIN_STEP_LABELS[key] || defaultLabel;
}
