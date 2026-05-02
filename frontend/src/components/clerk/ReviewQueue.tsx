import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getClerkQueue, reviewFiling, FilingEnvelope } from '../../api/filings';
import { getDemoCourtName } from '../auth/LoginScreen';

const COMMON_REASONS = [
  'Missing required documents',
  'Document not text-searchable (MCR 1.109)',
  'Incorrect filing fee',
  'Filed in wrong court',
  'Missing proof of service',
  'Document formatting does not comply with court rules',
  'Incomplete case information',
];

const REFRESH_MS = 30_000;

function ReviewQueue() {
  const queryClient = useQueryClient();
  const clerkCourtId = parseInt(localStorage.getItem('demo_court_id') || '3', 10);
  const clerkCourtName = getDemoCourtName() || '3rd Circuit Court - Wayne County';

  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedFiling, setSelectedFiling] = useState<FilingEnvelope | null>(null);
  const [reviewReason, setReviewReason] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [reviewError, setReviewError] = useState<string | null>(null);

  const queryKey = ['clerk-queue', clerkCourtId, statusFilter] as const;

  const { data, isFetching, dataUpdatedAt, refetch } = useQuery({
    queryKey,
    queryFn: () => getClerkQueue(clerkCourtId, 1, statusFilter),
    // React Query handles tab-visibility, focus refetch, and the polling cadence.
    refetchInterval: REFRESH_MS,
    refetchIntervalInBackground: false,
    staleTime: 5_000,
  });

  const filings = data?.filings ?? [];
  const total = data?.total ?? 0;
  const lastRefresh = dataUpdatedAt ? new Date(dataUpdatedAt) : new Date();

  const reviewMutation = useMutation({
    mutationFn: (vars: { filingId: number; action: 'accept' | 'reject' | 'return'; reason?: string }) =>
      reviewFiling(vars.filingId, vars.action, vars.reason),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  const handleReview = useCallback(
    async (filingId: number, action: 'accept' | 'reject' | 'return') => {
      setReviewError(null);
      try {
        await reviewMutation.mutateAsync({
          filingId,
          action,
          reason: action !== 'accept' ? reviewReason : undefined,
        });
        setSelectedFiling(null);
        setReviewReason('');
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Review failed';
        setReviewError(`Failed to ${action} filing #${filingId}: ${msg}`);
      }
    },
    [reviewMutation, reviewReason],
  );

  const handleBatchAccept = async () => {
    if (selectedIds.size === 0) return;
    setReviewError(null);
    const failed: number[] = [];
    // Sequential to keep clerk-side ordering deterministic and avoid hammering the API.
    for (const id of selectedIds) {
      try {
        await reviewMutation.mutateAsync({ filingId: id, action: 'accept' });
      } catch {
        failed.push(id);
      }
    }
    if (failed.length > 0) {
      setReviewError(`Failed to accept filing(s): ${failed.map(id => `#${id}`).join(', ')}`);
    }
    setSelectedIds(new Set());
  };

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filings.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filings.map(f => f.id)));
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleString();
  };

  const getAge = (dateStr: string | null): { text: string; level: string } => {
    if (!dateStr) return { text: 'N/A', level: '' };
    const hours = (Date.now() - new Date(dateStr).getTime()) / 3600000;
    if (hours < 2) return { text: `${Math.round(hours * 60)}m`, level: 'fresh' };
    if (hours < 24) return { text: `${Math.round(hours)}h`, level: 'normal' };
    if (hours < 48) return { text: '1d', level: 'aging' };
    return { text: `${Math.floor(hours / 24)}d`, level: 'overdue' };
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  const overdueCount = filings.filter(f => getAge(f.submitted_at).level === 'overdue').length;
  const actionInProgress = reviewMutation.isPending;

  return (
    <div className="clerk-review">
      <div className="clerk-header">
        <h2>Clerk Review Queue</h2>
        <div className="clerk-header-stats">
          <div className="stat-card">
            <span className="stat-number">{total}</span>
            <span className="stat-label">Pending</span>
          </div>
          <div className="stat-card">
            <span className="stat-number">{overdueCount}</span>
            <span className="stat-label">Overdue</span>
          </div>
        </div>
      </div>

      <div className="queue-controls">
        <div className="form-group">
          <label>Court</label>
          <span className="clerk-court-label">{clerkCourtName}</span>
        </div>
        <div className="form-group">
          <label htmlFor="statusFilter">Filter</label>
          <select
            id="statusFilter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Pending</option>
            <option value="submitted">New Submissions</option>
            <option value="under_review">Under Review</option>
          </select>
        </div>
        <button className="btn btn-secondary" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? 'Refreshing...' : 'Refresh'}
        </button>
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

      {/* Batch actions */}
      {selectedIds.size > 0 && (
        <div className="batch-actions">
          <span>{selectedIds.size} filing(s) selected</span>
          <button
            className="btn btn-success btn-small"
            onClick={handleBatchAccept}
            disabled={actionInProgress}
          >
            {actionInProgress ? 'Processing...' : `Accept ${selectedIds.size} Filing(s)`}
          </button>
          <button
            className="btn btn-secondary btn-small"
            onClick={() => setSelectedIds(new Set())}
          >
            Clear Selection
          </button>
        </div>
      )}

      <div className="queue-layout">
        <div className="queue-list">
          <table>
            <thead>
              <tr>
                <th className="th-checkbox">
                  <input
                    type="checkbox"
                    checked={selectedIds.size === filings.length && filings.length > 0}
                    onChange={toggleSelectAll}
                    aria-label="Select all filings"
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
                    className={`${selectedFiling?.id === filing.id ? 'selected' : ''} ${age.level === 'overdue' ? 'row-overdue' : ''}`}
                    onClick={() => setSelectedFiling(filing)}
                  >
                    <td className="td-checkbox" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(filing.id)}
                        onChange={() => toggleSelect(filing.id)}
                        aria-label={`Select filing ${filing.id}`}
                      />
                    </td>
                    <td className="filing-num">#{filing.id}</td>
                    <td className="filing-title">{filing.case_title || 'Untitled'}</td>
                    <td className="filing-date">{formatDate(filing.submitted_at)}</td>
                    <td>
                      <span className={`age-badge ${age.level}`}>{age.text}</span>
                    </td>
                    <td>{filing.documents.length}</td>
                    <td>
                      <span className={`status-badge ${filing.status}`}>
                        {filing.status.replace('_', ' ')}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {!isFetching && filings.length === 0 && (
                <tr>
                  <td colSpan={7} className="empty-queue">
                    No pending filings for this court. Queue is clear.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {selectedFiling && (
          <div className="filing-detail-panel">
            <div className="detail-panel-header">
              <h3>Filing #{selectedFiling.id}</h3>
              <span className={`status-badge ${selectedFiling.status}`}>
                {selectedFiling.status.replace('_', ' ')}
              </span>
            </div>

            <div className="detail-section">
              <h4>Case Information</h4>
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
                        {doc.document_type_code} &middot; {formatSize(doc.file_size_bytes)}
                        {doc.page_count && ` · ${doc.page_count} pages`}
                      </span>
                    </div>
                    <div className="doc-flags">
                      {!doc.is_text_searchable && doc.mime_type === 'application/pdf' && (
                        <span className="flag-badge warning">Not searchable</span>
                      )}
                      {doc.is_confidential && (
                        <span className="flag-badge confidential">Confidential</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="detail-section">
              <h4>Review Actions</h4>

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
                  onClick={() => handleReview(selectedFiling.id, 'accept')}
                  disabled={actionInProgress}
                >
                  {actionInProgress ? 'Processing...' : 'Accept'}
                </button>
                <button
                  className="btn btn-warning"
                  onClick={() => handleReview(selectedFiling.id, 'return')}
                  disabled={actionInProgress || !reviewReason.trim()}
                  title={!reviewReason.trim() ? 'Reason required' : ''}
                >
                  Return for Correction
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => handleReview(selectedFiling.id, 'reject')}
                  disabled={actionInProgress || !reviewReason.trim()}
                  title={!reviewReason.trim() ? 'Reason required' : ''}
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        )}

        {!selectedFiling && filings.length > 0 && (
          <div className="filing-detail-panel empty-detail">
            <p>Select a filing from the queue to review it.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default ReviewQueue;
