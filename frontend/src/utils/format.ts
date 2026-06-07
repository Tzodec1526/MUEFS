/** Format integer cents as a USD amount, e.g. 1500 -> "$15.00". */
export function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

/** Like formatCents, but renders a zero amount as "No fee". */
export function formatFee(cents: number): string {
  return cents === 0 ? 'No fee' : formatCents(cents);
}

/** Format a byte count, e.g. 124000 -> "121 KB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

/** Format an ISO date string as a short US date, e.g. "Jun 7, 2026". */
export function formatShortDate(d: string | null): string {
  if (!d) return '--';
  return new Date(d).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  });
}

const DOCUMENT_LABELS: Record<string, string> = {
  COMPLAINT: 'Complaint', SUMMONS: 'Summons', PETITION: 'Petition',
  INFORMATION: 'Information / Complaint', WARRANT: 'Warrant',
  PROOF_SERVICE: 'Proof of Service', POS_ELECTRONIC: 'Proof of Service',
  CERT_SERVICE: 'Certificate of Service', MOTION: 'Motion',
  BRIEF: 'Brief in Support', BRIEF_SUPPORT: 'Brief in Support',
  RESPONSE_BRIEF: 'Response Brief', REPLY_BRIEF: 'Reply Brief',
  PROPOSED_ORDER: 'Proposed Order', NOTICE_HEARING: 'Notice of Hearing',
  NOT_HEARING: 'Notice of Hearing', AFFIDAVIT: 'Affidavit', EXHIBIT: 'Exhibit',
  ANSWER: 'Answer', REPLY: 'Reply', JURY_DEMAND: 'Jury Demand',
  MOT_SD: 'Motion for Summary Disposition', MOT_DISMISS: 'Motion to Dismiss',
  MOT_COMPEL: 'Motion to Compel', MOT_PROTECTIVE: 'Motion for Protective Order',
  MOT_SANCTIONS: 'Motion for Sanctions', MOT_DEFAULT: 'Motion for Default',
  MOT_SJ: 'Motion for Summary Judgment', MOT_LIMINE: 'Motion in Limine',
  MOT_RECONSIDER: 'Motion for Reconsideration', MOT_RELIEF: 'Motion for Relief from Judgment',
  MOT_STAY: 'Motion to Stay', MOT_ADJOURN: 'Motion to Adjourn',
  MOT_INTERVENE: 'Motion to Intervene', MOT_AMEND: 'Motion to Amend',
  MOT_QUASH: 'Motion to Quash', MOT_TRANSFER: 'Motion to Transfer Venue',
  MOT_CONSOLIDATE: 'Motion to Consolidate', MOT_WITHDRAW: 'Motion to Withdraw',
  MOT_TRO: 'Motion for TRO', MOT_PRELIM_INJ: 'Motion for Preliminary Injunction',
  MOT_FEES: 'Motion for Attorney Fees', MOT_OTHER: 'Motion',
  DISC_CERT_GF: 'Good-Faith Discovery Certification', AFF_DEFAULT: 'Affidavit of Default',
};

/** Human label for a document type code, e.g. "MOT_SD" -> "Motion for Summary Disposition". */
export function getDocumentLabel(code: string): string {
  if (DOCUMENT_LABELS[code]) return DOCUMENT_LABELS[code];
  return code.replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());
}
