import { useState, useEffect, useRef, useContext } from 'react';
import { Link } from 'react-router-dom';
import { batchReview, getFiling, reviewFiling, FilingEnvelope, FilingSummary, ClerkQueue, ClerkQueueFilters } from '../../api/filings';
import { CourtContext, StaffCourtSelect } from '../auth/CourtSession';
import LoadError from '../common/LoadError';
import DocumentDownload from '../common/DocumentDownload';
import { formatBytes, getDocumentLabel, parseServerDate } from '../../utils/format';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';
import { useClerkQueue } from './useClerkQueue';

const ACTION_UNCONFIRMED = 'the request did not complete. Refresh the queue to check its current status before trying again.';
const BATCH_UNCONFIRMED = 'Could not accept the selected filings. Refresh the queue to check their current status before trying again.';

const sameFilters = (a: ClerkQueueFilters, b: ClerkQueueFilters) =>
  (a.status || 'all') === (b.status || 'all') && (a.search || '') === (b.search || '')
  && Boolean(a.waiting_48h_only) === Boolean(b.waiting_48h_only);

function ReviewQueue() {
  const { court } = useContext(CourtContext)!;
  usePageTitle('Review queue', court?.court_name);
  const courtId = court!.court_id;
  const [review, setReview] = useState<{
    id: number; filing?: FilingEnvelope; error?: LoadFailure;
  } | null>(null);
  const [actionInProgress, setActionInProgress] = useState(false);
  const {
    queue, loading, setLoading, queueError, filters, setFilters, page, setPage,
    selectedSubmissions, setSelectedSubmissions, fetchQueue,
  } = useClerkQueue(courtId, Boolean(review) || actionInProgress);
  const filings = queue?.filings ?? [];
  const total = queue?.total ?? 0;
  const pageCount = queue ? Math.ceil(queue.total / queue.page_size) : 0;
  const selectedFiling = review?.filing;
  const [reviewReason, setReviewReason] = useState('');
  const [filterDraft, setFilterDraft] = useState(filters);
  const statusFilter = filters.status;
  const filtersChanged = filterDraft.status !== filters.status || filterDraft.search !== filters.search
    || filterDraft.waiting_48h_only !== filters.waiting_48h_only;
  const canReview = selectedFiling
    && ['submitted', 'under_review'].includes(selectedFiling.status)
    && statusFilter !== 'waivers';
  const reviewRequestRef = useRef<AbortController | null>(null);
  const reviewHeading = useRef<HTMLHeadingElement>(null);
  const queueHeading = useRef<HTMLHeadingElement>(null);
  // Where the processed filings were, so focus can follow the queue once it reloads.
  const focusAfterRefresh = useRef<{ index: number; queue: ClerkQueue | null } | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);

  useEffect(() => () => reviewRequestRef.current?.abort(), []);
  useEffect(() => {
    if (review?.filing || review?.error) reviewHeading.current?.focus();
  }, [review]);

  // An action removes the control that had focus. Once the queue reloads, focus the row that
  // took the first processed filing's place (the next one), or the heading if none remain.
  useEffect(() => {
    const pending = focusAfterRefresh.current;
    if (!pending || loading || queue === pending.queue) return;
    focusAfterRefresh.current = null;
    const rows = queue?.filings ?? [];
    const next = rows[Math.min(pending.index, rows.length - 1)];
    (next ? document.getElementById(`queue-filing-${next.id}`) : queueHeading.current)?.focus();
  }, [queue, loading]);

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
      focusAfterRefresh.current = { index: Math.max(0, filings.findIndex(item => item.id === filing.id)), queue };
      closeReview();
      await fetchQueue();
    } catch (err) {
      setReviewError(`Failed to ${action} filing #${filing.id}: ${errorMessage(err, ACTION_UNCONFIRMED)}`);
      // The browser drops focus from a button disabled while the action ran; return it to the review.
      if (!document.activeElement || document.activeElement === document.body) reviewHeading.current?.focus();
    } finally {
      setActionInProgress(false);
    }
  }

  async function handleBatchAccept() {
    if (selectedSubmissions.size === 0) return;
    const firstSelected = Math.max(0, filings.findIndex(item => selectedSubmissions.has(item.id)));
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
      setReviewError(errorMessage(err, BATCH_UNCONFIRMED));
    } finally {
      // Clearing the selection removes the batch bar and its focused button.
      focusAfterRefresh.current = { index: firstSelected, queue };
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
    if (loading || actionInProgress || selectedFiling?.id === filingId) return;
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
        error: loadFailure(err, "We couldn't load this filing. Please retry."),
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

  const ageAsOf = queue ? parseServerDate(queue.as_of).getTime() : 0;
  const getAge = (dateStr: string | null): { text: string; level: string } => {
    if (!dateStr) return { text: 'N/A', level: '' };
    const minutes = Math.max(0, (ageAsOf - parseServerDate(dateStr).getTime()) / 60000);
    return {
      text: minutes < 1 ? 'just now' : minutes < 60 ? `${Math.floor(minutes)}m`
        : minutes < 1440 ? `${Math.floor(minutes / 60)}h` : `${Math.floor(minutes / 1440)}d`,
      level: minutes >= 2880 ? 'aging' : minutes < 120 ? 'fresh' : 'normal',
    };
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
        <PageHeading headingRef={queueHeading}>Clerk Review Queue</PageHeading>
        <div className="clerk-header-stats">
          <div className="stat-card">
            <span className="stat-number">{queue ? total : '—'}</span>
            <span className="stat-label">Matching filings</span>
          </div>
          <div className="stat-card">
            <span className="stat-number">{queue?.waiting_48h ?? '—'}</span>
            <span className="stat-label">Waiting 48+ hours</span>
          </div>
        </div>
      </div>

      <div className="queue-controls">
        <form
          className="queue-filter"
          onSubmit={(e) => {
            e.preventDefault();
            const fields = new FormData(e.currentTarget);
            const submitted: ClerkQueueFilters = {
              status: String(fields.get('status') ?? 'all'),
              search: String(fields.get('search') ?? '').trim(),
              waiting_48h_only: fields.get('waiting_48h_only') !== null,
            };
            if (!sameFilters(submitted, filters)) {
              setLoading(true);
              setFilters(submitted);
              setFilterDraft(submitted);
              setPage(1);
              setSelectedSubmissions(new Map());
              closeReview();
            } else void fetchQueue();
          }}
        >
          <div className="form-group">
            <label htmlFor="statusFilter">Filter</label>
            <select
              id="statusFilter"
              name="status"
              value={filterDraft.status}
              onChange={(e) => setFilterDraft(previous => ({ ...previous, status: e.target.value }))}
              disabled={actionInProgress}
            >
              <option value="all">All Pending</option>
              <option value="submitted">New Submissions</option>
              <option value="under_review">Under Review</option>
              <option value="waivers">Pending Fee Waivers</option>
            </select>
          </div>
          <div className="form-group queue-search">
            <label htmlFor="queueSearch">Case title, case number or #filing number</label>
            <input id="queueSearch" name="search" type="search" maxLength={200}
              placeholder="Example: Smith or #123" value={filterDraft.search}
              disabled={actionInProgress}
              onChange={e => setFilterDraft(previous => ({ ...previous, search: e.target.value }))} />
          </div>
          <label className="queue-age-filter">
            <input type="checkbox" name="waiting_48h_only" checked={filterDraft.waiting_48h_only}
              disabled={actionInProgress}
              onChange={e => setFilterDraft(previous => ({ ...previous, waiting_48h_only: e.target.checked }))} />
            Waiting at least 48 hours
          </label>
          <button type="submit" className="btn btn-secondary" disabled={loading || actionInProgress}>
            {loading ? 'Loading...' : filtersChanged ? 'Apply filters' : 'Refresh'}
          </button>
        </form>
        {queue && <span className="queue-meta">
          Measured: {formatDate(queue.as_of)}. {queue.oldest_submitted_at && <>Oldest matching receipt: {formatDate(queue.oldest_submitted_at)}. </>}
          Ages are elapsed time since receipt.
        </span>}
      </div>

      {reviewError && (
        <div className="alert alert-error" role="alert">
          {reviewError}
          <button className="btn btn-small" onClick={() => setReviewError(null)} style={{ marginLeft: '1rem' }}>Dismiss</button>
        </div>
      )}

      {queueError && <LoadError failure={queueError} onRetry={fetchQueue} />}

      {/* Batch actions */}
      {selectedSubmissions.size > 0 && statusFilter !== 'waivers' && (
        <div className="batch-actions">
          <span>{selectedSubmissions.size} filing(s) selected</span>
          <button
            className="btn btn-success btn-small"
            onClick={handleBatchAccept}
            disabled={loading || actionInProgress}
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

      <div className={`queue-layout${review ? ' review-open' : ''}`} aria-busy={loading}>
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
                    disabled={loading || actionInProgress || statusFilter === 'waivers'}
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
                    id={`queue-filing-${filing.id}`}
                    className={review?.id === filing.id ? 'selected' : ''}
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
                        disabled={loading || actionInProgress || statusFilter === 'waivers'}
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
                    No filings match these filters in this court.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {pageCount > 1 && (
            <div className="pagination">
              <button className="btn btn-secondary btn-small" disabled={page <= 1 || loading || actionInProgress}
                onClick={() => { setLoading(true); setPage((p) => p - 1); setSelectedSubmissions(new Map()); closeReview(); }}>
                Previous
              </button>
              <span>Page {page} of {pageCount}</span>
              <button className="btn btn-secondary btn-small" disabled={page >= pageCount || loading || actionInProgress}
                onClick={() => { setLoading(true); setPage((p) => p + 1); setSelectedSubmissions(new Map()); closeReview(); }}>
                Next
              </button>
            </div>
          )}
        </div>

        {/* Filing Detail Panel */}
        {review && (
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

      </div>
    </div>
  );
}

export default ReviewQueue;
