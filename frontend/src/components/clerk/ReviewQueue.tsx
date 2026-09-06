import { useState, useEffect, useCallback, useRef, useContext } from 'react';
import { Link } from 'react-router-dom';
import { batchReview, getClerkQueue, getFiling, reviewFiling, FilingEnvelope, FilingSummary } from '../../api/filings';
import { CourtContext, StaffCourtSelect } from '../auth/CourtSession';
import LoadError from '../common/LoadError';
import DocumentDownload from '../common/DocumentDownload';
import { formatBytes, getDocumentLabel, parseServerDate } from '../../utils/format';
import { getErrorDetail } from '../../utils/errors';

function ReviewQueue() {
  const { court } = useContext(CourtContext)!;
  const courtId = court!.court_id;
  const [filings, setFilings] = useState<FilingSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [review, setReview] = useState<{
    id: number; filing?: FilingEnvelope; error?: string;
  } | null>(null);
  const selectedFiling = review?.filing;
  const [loading, setLoading] = useState(false);
  const [reviewReason, setReviewReason] = useState('');
  const [actionInProgress, setActionInProgress] = useState(false);
  const [selectedSubmissions, setSelectedSubmissions] = useState<Map<number, number>>(new Map());
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const canReview = selectedFiling
    && ['submitted', 'under_review'].includes(selectedFiling.status)
    && statusFilter !== 'waivers';
  const [page, setPage] = useState(1);
  const requestRef = useRef<AbortController | null>(null);
  const reviewRequestRef = useRef<AbortController | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);

  const fetchQueue = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setQueueError(null);
    try {
      const result = await getClerkQueue(courtId, page, statusFilter, controller.signal);
      if (controller.signal.aborted) return;
      if (page > 1 && result.filings.length === 0) {
        setPage(Math.max(1, Math.ceil(result.total / 25)));
        return;
      }
      setFilings(result.filings);
      setTotal(result.total);
      setSelectedSubmissions(previous => new Map(result.filings
        .filter(filing => previous.get(filing.id) === filing.submission_count)
        .map(filing => [filing.id, filing.submission_count])));
      setLastRefresh(new Date());
    } catch {
      if (controller.signal.aborted) return;
      setQueueError("We couldn't load the review queue. Please retry.");
      setFilings([]);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [courtId, page, statusFilter]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- existing pattern; fetchQueue performs the setState for loading/data
    fetchQueue();
    return () => requestRef.current?.abort();
  }, [fetchQueue]);

  useEffect(() => () => reviewRequestRef.current?.abort(), []);

  // Auto-refresh every 30 seconds, but never while a filing is open for review or an
  // action is in flight -- a refresh mid-review would clobber the clerk's work.
  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden && !review && !actionInProgress) fetchQueue();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchQueue, review, actionInProgress]);

  async function handleReview(filing: FilingEnvelope, action: 'accept' | 'reject' | 'return') {
    if (action === 'reject' && !window.confirm(
      'Reject is final — the filer cannot resubmit under this envelope. If they should fix and re-file, use "Return for Correction" instead. Reject this filing?'
    )) {
      return;
    }
    setActionInProgress(true);
    setReviewError(null);
    try {
      await reviewFiling(filing, action, action !== 'accept' ? reviewReason : undefined);
      closeReview();
      await fetchQueue();
    } catch (err) {
      const msg = getErrorDetail(err) || (err instanceof Error ? err.message : 'Review failed');
      setReviewError(`Failed to ${action} filing #${filing.id}: ${msg}`);
    } finally {
      setActionInProgress(false);
    }
  }

  async function handleBatchAccept() {
    if (selectedSubmissions.size === 0) return;
    setActionInProgress(true);
    setReviewError(null);
    try {
      const res = await batchReview(
        Array.from(selectedSubmissions, ([id, submission_count]) => ({ id, submission_count })),
        'accept',
      );
      if (res.failed.length > 0) {
        setReviewError(res.failed.map(id => `Filing #${id}: ${res.errors[id]}`).join(' '));
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Batch accept failed';
      setReviewError(msg);
    } finally {
      setSelectedSubmissions(new Map());
      setActionInProgress(false);
      await fetchQueue();
    }
  }

  function closeReview() {
    reviewRequestRef.current?.abort();
    setReview(null);
    setReviewReason('');
    setReviewError(null);
  }

  async function openReview(filingId: number) {
    if (actionInProgress || selectedFiling?.id === filingId) return;
    reviewRequestRef.current?.abort();
    const controller = new AbortController();
    reviewRequestRef.current = controller;
    setReview({ id: filingId });
    setReviewReason('');
    setReviewError(null);
    try {
      const filing = await getFiling(filingId, controller.signal);
      if (!controller.signal.aborted) setReview({ id: filingId, filing });
    } catch (err) {
      if (!controller.signal.aborted) setReview({
        id: filingId,
        error: getErrorDetail(err) || "We couldn't load this filing. Please retry.",
      });
    }
  }

  const toggleSelect = (filing: FilingSummary) => {
    setSelectedSubmissions(prev => {
      const next = new Map(prev);
      if (next.has(filing.id)) next.delete(filing.id);
      else next.set(filing.id, filing.submission_count);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedSubmissions.size === filings.length) {
      setSelectedSubmissions(new Map());
    } else {
      setSelectedSubmissions(new Map(filings.map(f => [f.id, f.submission_count])));
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    return parseServerDate(dateStr).toLocaleString();
  };

  const getAge = (dateStr: string | null): { text: string; level: string } => {
    if (!dateStr) return { text: 'N/A', level: '' };
    // eslint-disable-next-line react-hooks/purity -- age computation is intentionally live at render time for queue freshness display
    const minutes = Math.max(0, (Date.now() - parseServerDate(dateStr).getTime()) / 60000);
    if (minutes < 1) return { text: 'just now', level: 'fresh' };
    if (minutes < 120) return { text: `${Math.round(minutes)}m`, level: 'fresh' };
    const hours = minutes / 60;
    if (hours < 24) return { text: `${Math.round(hours)}h`, level: 'normal' };
    if (hours < 48) return { text: '1d', level: 'aging' };
    return { text: `${Math.floor(hours / 24)}d`, level: 'overdue' };
  };

  // Common rejection reasons for quick selection
  const COMMON_REASONS = [
    'Missing required documents',
    'Document not text-searchable (MCR 1.109)',
    'Incorrect filing fee',
    'Filed in wrong court',
    'Missing proof of service',
    'Document formatting does not comply with court rules',
    'Incomplete case information',
  ];

  return (
    <div className="clerk-review">
      <StaffCourtSelect disabled={!!review || actionInProgress} />
      <div className="clerk-header">
        <h2>Clerk Review Queue</h2>
        <div className="clerk-header-stats">
          <div className="stat-card">
            <span className="stat-number">{total}</span>
            <span className="stat-label">Pending</span>
          </div>
          <div className="stat-card">
            <span className="stat-number">{filings.filter(f => {
              const age = getAge(f.submitted_at);
              return age.level === 'overdue';
            }).length}</span>
            <span className="stat-label">Overdue on this page</span>
          </div>
        </div>
      </div>

      <div className="queue-controls">
        <form
          className="queue-webmcp-filter"
          toolname="get_clerk_review_queue"
          tooldescription="List filings pending clerk review, optionally filtered by status"
          onSubmit={(e) => {
            e.preventDefault();
            void fetchQueue();
          }}
        >
          <div className="form-group">
            <label htmlFor="statusFilter">Filter</label>
            <select
              id="statusFilter"
              name="status"
              toolparamdescription="Queue status filter: all, submitted, or under_review"
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(1); setSelectedSubmissions(new Map()); closeReview(); }}
              disabled={actionInProgress}
            >
              <option value="all">All Pending</option>
              <option value="submitted">New Submissions</option>
              <option value="under_review">Under Review</option>
              <option value="waivers">Pending Fee Waivers</option>
            </select>
          </div>
          <button type="submit" className="btn btn-secondary" disabled={loading}>
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </form>
        <span className="queue-meta">
          Last updated: {lastRefresh.toLocaleTimeString()}
        </span>
      </div>

      {reviewError && (
        <div className="alert alert-error" role="alert">
          {reviewError}
          <button className="btn btn-small" onClick={() => setReviewError(null)} style={{ marginLeft: '1rem' }}>Dismiss</button>
        </div>
      )}

      {queueError && <LoadError message={queueError} onRetry={fetchQueue} />}

      {/* Batch actions */}
      {selectedSubmissions.size > 0 && statusFilter !== 'waivers' && (
        <div className="batch-actions">
          <span>{selectedSubmissions.size} filing(s) selected</span>
          <button
            className="btn btn-success btn-small"
            onClick={handleBatchAccept}
            disabled={actionInProgress}
          >
            {actionInProgress ? 'Processing...' : `Accept ${selectedSubmissions.size} Filing(s)`}
          </button>
          <button
            className="btn btn-secondary btn-small"
            onClick={() => setSelectedSubmissions(new Map())}
          >
            Clear Selection
          </button>
        </div>
      )}

      <div className="queue-layout">
        {/* Filing List */}
        <div className="queue-list">
          <table>
            <thead>
              <tr>
                <th className="th-checkbox">
                  <input
                    type="checkbox"
                    checked={selectedSubmissions.size === filings.length && filings.length > 0}
                    onChange={toggleSelectAll}
                    aria-label="Select all filings"
                    disabled={actionInProgress || statusFilter === 'waivers'}
                  />
                </th>
                <th>Filing #</th>
                <th>Case Title</th>
                <th>Submitted</th>
                <th>Age</th>
                <th>Docs</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filings.map((filing) => {
                const age = getAge(filing.submitted_at);
                return (
                  <tr
                    key={filing.id}
                    className={`${review?.id === filing.id ? 'selected' : ''} ${age.level === 'overdue' ? 'row-overdue' : ''}`}
                    onClick={() => openReview(filing.id)}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && e.target === e.currentTarget) openReview(filing.id);
                    }}
                  >
                    <td className="td-checkbox" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedSubmissions.has(filing.id)}
                        onChange={() => toggleSelect(filing)}
                        aria-label={`Select filing ${filing.id}`}
                        disabled={actionInProgress || statusFilter === 'waivers'}
                      />
                    </td>
                    <td className="filing-num">#{filing.id}</td>
                    <td className="filing-title">{filing.case_title || 'Untitled'}</td>
                    <td className="filing-date">{formatDate(filing.submitted_at)}</td>
                    <td>
                      <span className={`age-badge ${age.level}`}>{age.text}</span>
                    </td>
                    <td>{filing.document_count}</td>
                    <td>
                      <span className={`status-badge ${filing.status}`}>
                        {filing.status.replace('_', ' ')}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {!loading && !queueError && filings.length === 0 && (
                <tr>
                  <td colSpan={7} className="empty-queue">
                    No pending filings for this court. Queue is clear.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {total > 25 && (
            <div className="pagination">
              <button className="btn btn-secondary btn-small" disabled={page <= 1 || loading || actionInProgress}
                onClick={() => { setPage((p) => p - 1); setSelectedSubmissions(new Map()); closeReview(); }}>
                Previous
              </button>
              <span>Page {page} of {Math.ceil(total / 25)}</span>
              <button className="btn btn-secondary btn-small" disabled={page >= Math.ceil(total / 25) || loading || actionInProgress}
                onClick={() => { setPage((p) => p + 1); setSelectedSubmissions(new Map()); closeReview(); }}>
                Next
              </button>
            </div>
          )}
        </div>

        {/* Filing Detail Panel */}
        {review && (
          <div className="filing-detail-panel">
            <div className="detail-panel-header">
              <h3>Filing #{review.id}</h3>
              {selectedFiling && <span className={`status-badge ${selectedFiling.status}`}>
                {selectedFiling.status.replace('_', ' ')}
              </span>}
              <button type="button" className="btn btn-secondary btn-small" disabled={actionInProgress}
                onClick={closeReview}>
                Close review
              </button>
            </div>
            {!selectedFiling && !review.error && <p role="status">Loading filing details…</p>}
            {review.error && <LoadError message={review.error} onRetry={() => openReview(review.id)} />}
            {selectedFiling && <>
            {!canReview && statusFilter !== 'waivers' && <p role="status">
              This filing is no longer awaiting intake review. Refresh the queue for current work.
            </p>}
            <div className="detail-section">
              <h4>Case Information</h4>
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
                <div><label>Submitted</label><span>{formatDate(selectedFiling.submitted_at)}</span></div>
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
              <h4>Review Actions</h4>

              {/* Quick reason selector */}
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
        )}

        {!review && filings.length > 0 && (
          <div className="filing-detail-panel empty-detail">
            <p>Select a filing from the queue to review it.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default ReviewQueue;
