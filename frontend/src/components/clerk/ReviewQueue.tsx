import { useState, useEffect, useRef, useContext } from 'react';
import { batchReview, getFiling, reviewFiling, FilingEnvelope, FilingSummary, ClerkQueue } from '../../api/filings';
import { CourtContext, StaffCourtSelect } from '../auth/CourtSession';
import LoadError from '../common/LoadError';
import { formatDateTime, parseServerDate, plural } from '../../utils/format';
import { filingStatusLabel } from '../../utils/filingStatus';
import { errorMessage, loadFailure, type LoadFailure } from '../../utils/errors';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';
import { focusQueueRow, useClerkQueue } from './useClerkQueue';
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
    queue, loading, startLoading, queueError, filters, setFilters, page, setPage,
    selectedSubmissions, setSelectedSubmissions, fetchQueue,
  } = useClerkQueue(courtId, Boolean(review) || actionInProgress);
  const filings = queue?.filings ?? [];
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
    if (next) focusQueueRow(next.id);
    else queueHeading.current?.focus();
  }, [queue, loading]);

  async function handleReview(filing: FilingEnvelope, action: 'accept' | 'reject' | 'return') {
    if (action === 'reject' && !window.confirm(
      'Reject is final. The filer cannot resubmit this filing. If they should fix it and file again, use "Return for correction" instead. Reject this filing?'
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
      <div className="clerk-header">
        <PageHeading headingRef={queueHeading}>Review queue</PageHeading>
        <StaffCourtSelect disabled={!!review || actionInProgress} />
      </div>

      <div className="queue-controls">
        <QueueFilters
          filters={filters}
          loading={loading}
          actionInProgress={actionInProgress}
          onApply={(submitted) => {
            startLoading();
            setFilters(submitted);
            setPage(1);
            setSelectedSubmissions(new Map());
            closeReview();
          }}
          onRefresh={() => void fetchQueue()}
        />
      </div>

      {queue && <p className="queue-meta">
        {plural(queue.total, 'matching filing')} · {queue.waiting_48h} waiting at least 48 hours
        {queue.oldest_submitted_at && ` · Oldest received ${formatDateTime(queue.oldest_submitted_at)}`}
      </p>}

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
          <span>{plural(selectedSubmissions.size, 'filing')} selected</span>
          <button
            className="btn btn-success btn-small"
            onClick={handleBatchAccept}
            disabled={loading || actionInProgress}
          >
            {actionInProgress ? 'Processing...' : `Accept ${plural(selectedSubmissions.size, 'filing')}`}
          </button>
          <button
            className="btn btn-secondary btn-small"
            onClick={() => setSelectedSubmissions(new Map())}
          >
            Clear selection
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
                  <label className="queue-select-all">
                    <input
                      type="checkbox"
                      checked={selectedSubmissions.size === filings.length && filings.length > 0}
                      onChange={toggleSelectAll}
                      aria-label="Select all filings"
                      disabled={loading || actionInProgress || statusFilter === 'waivers'}
                    />
                    <span aria-hidden="true">Select all</span>
                  </label>
                </th>
                <th>Filing</th>
                <th>Case title</th>
                <th>Submitted</th>
                <th>Age</th>
                <th>Documents</th>
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
                    <td className="filing-num">
                      <button
                        type="button"
                        className="queue-review-button"
                        onClick={(e) => { e.stopPropagation(); openReview(filing.id); }}
                      >
                        Review filing #{filing.id}
                      </button>
                    </td>
                    <td className="filing-title" data-label="Case title">{filing.case_title || 'Untitled'}</td>
                    <td className="filing-date" data-label="Submitted">{formatDateTime(filing.submitted_at)}</td>
                    <td data-label="Age">
                      <span className={`age-badge ${age.level}`}>{age.text}</span>
                    </td>
                    <td data-label="Documents">{filing.document_count}</td>
                    <td data-label="Status">
                      <span className={`status-badge ${filing.status}`}>
                        {filingStatusLabel(filing.status)}
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
                onClick={() => { startLoading(); setPage((p) => p - 1); setSelectedSubmissions(new Map()); closeReview(); }}>
                Previous
              </button>
              <span>Page {page} of {pageCount}</span>
              <button className="btn btn-secondary btn-small" disabled={page >= pageCount || loading || actionInProgress}
                onClick={() => { startLoading(); setPage((p) => p + 1); setSelectedSubmissions(new Map()); closeReview(); }}>
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
