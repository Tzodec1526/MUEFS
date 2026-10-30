import { useState, useEffect, useRef, useContext } from 'react';
import { batchReview, getFiling, reviewFiling, FilingEnvelope, FilingSummary, ClerkQueue } from '../../api/filings';
import { CourtContext, StaffCourtSelect } from '../auth/CourtSession';
import LoadError from '../common/LoadError';
import { formatServerDateTime, parseServerDate } from '../../utils/format';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';
import { useClerkQueue } from './useClerkQueue';
import QueueFilters from './QueueFilters';
import FilingReviewPanel from './FilingReviewPanel';

const ACTION_UNCONFIRMED = 'the request did not complete. Refresh the queue to check its current status before trying again.';
const BATCH_UNCONFIRMED = 'Could not accept the selected filings. Refresh the queue to check their current status before trying again.';

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
  const statusFilter = filters.status;
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
        <QueueFilters
          filters={filters}
          loading={loading}
          actionInProgress={actionInProgress}
          onApply={(submitted) => {
            setLoading(true);
            setFilters(submitted);
            setPage(1);
            setSelectedSubmissions(new Map());
            closeReview();
          }}
          onRefresh={() => void fetchQueue()}
        />
        {queue && <span className="queue-meta">
          Measured: {formatServerDateTime(queue.as_of)}. {queue.oldest_submitted_at && <>Oldest matching receipt: {formatServerDateTime(queue.oldest_submitted_at)}. </>}
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
                    <td className="filing-date">{formatServerDateTime(filing.submitted_at)}</td>
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

        {review && (
          <FilingReviewPanel
            review={review}
            canReview={Boolean(canReview)}
            statusFilter={statusFilter}
            actionInProgress={actionInProgress}
            reviewReason={reviewReason}
            setReviewReason={setReviewReason}
            reviewHeading={reviewHeading}
            closeReview={closeReview}
            openReview={openReview}
            handleReview={handleReview}
          />
        )}

      </div>
    </div>
  );
}

export default ReviewQueue;
