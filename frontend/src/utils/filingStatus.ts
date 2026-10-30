export const FILING_STATUS_LABELS: Record<string, string> = {
  draft: 'Draft', submitted: 'Submitted', under_review: 'Under review',
  accepted: 'Accepted', rejected: 'Rejected', returned: 'Returned', served: 'Service documents recorded',
};

const FILING_TYPE_LABELS: Record<string, string> = {
  initial: 'New case', subsequent: 'Existing case', motion: 'Existing case', service_only: 'Service only',
};

const FEE_SOURCE_LABELS: Record<string, string> = {
  court: 'Court assessment', waiver: 'Fee waiver decision', demo: 'Demo example amount',
  service_only: 'Service-only record', unassessed: 'Not assessed',
};

export function filingStatusLabel(status: string): string {
  return FILING_STATUS_LABELS[status] || status;
}

export function filingTypeLabel(type: string): string {
  return FILING_TYPE_LABELS[type] || type;
}

export function feeSourceLabel(source: string): string {
  return FEE_SOURCE_LABELS[source] || source;
}
