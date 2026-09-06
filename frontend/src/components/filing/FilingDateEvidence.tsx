import type { FilingDateBasis } from '../../api/filings';
import { formatCourtDate } from '../../utils/format';
import DocumentDownload from '../common/DocumentDownload';

export default function FilingDateEvidence({ basis }: { basis: FilingDateBasis }) {
  if (basis.source === 'court_order') return <div className="receipt-date-basis">
    <p>Established by court order signed {formatCourtDate(basis.order_signed_date)}.</p>
    <p>{basis.authority_reference}</p>
    <DocumentDownload id={basis.order_document_id} title="Signed filing-date order" />
  </div>;
  return <div className="receipt-date-basis">
    {basis.error && <p className="alert alert-warning">{basis.error}</p>}
    {basis.timezone && <p>Court timezone: {basis.timezone} · Calendar revisions: {basis.calendar_ids.join(', ')}</p>}
    {Object.entries(basis.skipped_dates).map(([day, reason]) =>
      <p key={day}>{formatCourtDate(day)}: {reason}</p>)}
  </div>;
}
