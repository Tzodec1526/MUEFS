export const FILING_STATUS_LABELS: Record<string, string> = {
  draft: 'Draft', submitted: 'Submitted', under_review: 'Under review',
  accepted: 'Accepted', rejected: 'Rejected', returned: 'Returned', served: 'Service documents recorded',
};

export function filingStatusLabel(status: string): string {
  return FILING_STATUS_LABELS[status] || status;
}
