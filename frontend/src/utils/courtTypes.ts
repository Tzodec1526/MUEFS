const COURT_TYPE_LABELS: Record<string, string> = {
  circuit: 'Circuit Court',
  district: 'District Court',
  probate: 'Probate Court',
  court_of_claims: 'Court of Claims',
  court_of_appeals: 'Court of Appeals',
  supreme_court: 'Supreme Court',
  municipal: 'Municipal Court',
};

export function courtTypeLabel(type: string): string {
  return COURT_TYPE_LABELS[type] || type;
}
