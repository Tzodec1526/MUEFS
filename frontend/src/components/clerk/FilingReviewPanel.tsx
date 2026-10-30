import type { RefObject } from 'react';
import { Link } from 'react-router-dom';
import type { FilingEnvelope } from '../../api/filings';
import LoadError from '../common/LoadError';
import DocumentDownload from '../common/DocumentDownload';
import { formatBytes, formatServerDateTime, getDocumentLabel } from '../../utils/format';
import type { LoadFailure } from '../../utils/errors';

const COMMON_REASONS = [
  'Missing required documents',
  'Document not text-searchable (MCR 1.109)',
  'Incorrect filing fee',
  'Filed in wrong court',
  'Missing proof of service',
  'Document formatting does not comply with court rules',
  'Incomplete case information',
];

interface FilingReviewPanelProps {
  review: { id: number; filing?: FilingEnvelope; error?: LoadFailure };
  canReview: boolean;
  statusFilter: string | undefined;
  actionInProgress: boolean;
  reviewReason: string;
  setReviewReason: (reason: string) => void;
  reviewHeading: RefObject<HTMLHeadingElement>;
  closeReview: () => void;
  openReview: (filingId: number) => void;
  handleReview: (filing: FilingEnvelope, action: 'accept' | 'reject' | 'return') => void;
}

function FilingReviewPanel({
  review, canReview, statusFilter, actionInProgress, reviewReason, setReviewReason, reviewHeading,
  closeReview, openReview, handleReview,
}: FilingReviewPanelProps) {
  const selectedFiling = review.filing;
  return (
    <div className="filing-detail-panel">
      <div className="detail-panel-header">
        <h3 ref={reviewHeading} tabIndex={-1}>Filing #{review.id}</h3>
        {selectedFiling && <span className={`status-badge ${selectedFiling.status}`}>
          {selectedFiling.status.replace('_', ' ')}
        </span>}
        <button type="button" className="btn btn-secondary btn-small" disabled={actionInProgress}
          onClick={() => {
            closeReview();
            document.getElementById(`queue-filing-${review.id}`)?.focus();
          }}>
          Close review
        </button>
      </div>
      {!selectedFiling && !review.error && <p role="status">Loading filing details…</p>}
      {review.error && <LoadError failure={review.error} onRetry={() => openReview(review.id)} />}
      {selectedFiling && <>
      {!canReview && statusFilter !== 'waivers' && <p role="status">
        This filing is no longer awaiting intake review. Refresh the queue for current work.
      </p>}
      <div className="detail-section">
        <h4>Case information</h4>
        <p>{selectedFiling.submission_count ? `Reviewing submission ${selectedFiling.submission_count}` : 'Reviewing a legacy submission without a recorded submission number'}</p>
        <Link to={`/filings/${selectedFiling.id}/history`} className="btn btn-secondary btn-small">Receipts &amp; history</Link>
        {selectedFiling.fee_waiver_requested && <p>
          Fee waiver: {selectedFiling.fee_waiver_granted === true ? 'granted'
            : selectedFiling.fee_waiver_granted === false ? 'denied'
            : selectedFiling.fee_waiver_referred_at ? 'awaiting judicial review' : 'awaiting court review'}.
          {' '}<Link to={`/filings/${selectedFiling.id}/history`}>Open fee waiver review</Link>
        </p>}
        <div className="detail-grid">
          <div><label>Title</label><span>{selectedFiling.case_title || 'N/A'}</span></div>
          <div><label>Submitted</label><span>{formatServerDateTime(selectedFiling.submitted_at)}</span></div>
          <div><label>Filer ID</label><span>#{selectedFiling.filer_id}</span></div>
        </div>
        {selectedFiling.filing_description && (
          <div className="detail-description">
            <label>Description</label>
            <p>{selectedFiling.filing_description}</p>
          </div>
        )}
      </div>

      <div className="detail-section">
        <h4>Documents ({selectedFiling.documents.length})</h4>
        <div className="doc-list">
          {selectedFiling.documents.map((doc) => (
            <div key={doc.id} className="doc-item">
              <div className="doc-info">
                <strong>{doc.title}</strong>
                <span className="doc-meta">
                  {getDocumentLabel(doc.document_type_code)} &middot; {formatBytes(doc.file_size_bytes)}
                  {doc.page_count && ` \u00b7 ${doc.page_count} pages`}
                </span>
              </div>
              <div className="doc-flags">
                {!doc.is_text_searchable && doc.mime_type === 'application/pdf' && (
                  <span className="flag-badge warning">Not searchable</span>
                )}
                {doc.is_confidential && (
                  <span className="flag-badge confidential">Confidential</span>
                )}
                <DocumentDownload id={doc.id} title={doc.title} />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="detail-section">
        <h4>Review actions</h4>

        <div className="form-group">
          <label htmlFor="quickReason">Reason (required for reject/return)</label>
          <select
            id="quickReason"
            value={reviewReason}
            onChange={(e) => setReviewReason(e.target.value)}
          >
            <option value="">-- Select common reason --</option>
            {COMMON_REASONS.map((reason, i) => (
              <option key={i} value={reason}>{reason}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <textarea
            value={reviewReason}
            onChange={(e) => setReviewReason(e.target.value)}
            rows={3}
            placeholder="Or type a custom reason..."
            aria-label="Review reason"
          />
        </div>

        <div className="review-buttons">
          <button
            className="btn btn-success"
            onClick={() => handleReview(selectedFiling, 'accept')}
            disabled={actionInProgress || !canReview}
          >
            {actionInProgress ? 'Processing...' : 'Accept'}
          </button>
          <button
            className="btn btn-warning"
            onClick={() => handleReview(selectedFiling, 'return')}
            disabled={actionInProgress || !reviewReason.trim() || !canReview}
            title={!reviewReason.trim() ? 'Reason required' : ''}
          >
            Return for Correction
          </button>
          <button
            className="btn btn-danger"
            onClick={() => handleReview(selectedFiling, 'reject')}
            disabled={actionInProgress || !reviewReason.trim() || !canReview}
            title={!reviewReason.trim() ? 'Reason required' : ''}
          >
            Reject
          </button>
        </div>
        <p className="info-text review-action-note">
          <strong>Return for Correction</strong> sends it back so the filer can fix and
          re-file; the earlier submission remains in their history. <strong>Reject</strong> is final.
        </p>
      </div>
      </>}
    </div>
  );
}

export default FilingReviewPanel;
