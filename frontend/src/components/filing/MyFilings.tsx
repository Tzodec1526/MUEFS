import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { listFilings, FilingSummary } from '../../api/filings';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import { FILING_STATUS_LABELS, filingStatusLabel } from '../../utils/filingStatus';
import { formatDateTime, plural } from '../../utils/format';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

const STATUSES = Object.keys(FILING_STATUS_LABELS);

function MyFilings() {
  usePageTitle('My filings');
  const navigate = useNavigate();
  const [filings, setFilings] = useState<FilingSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedStatus = searchParams.get('status') ?? '';
  const statusFilter = STATUSES.includes(requestedStatus) ? requestedStatus : '';
  const setStatusFilter = (status: string) => setSearchParams(status ? { status } : {});
  const [page, setPage] = useState(1);
  const [pageStatus, setPageStatus] = useState(statusFilter);
  if (pageStatus !== statusFilter) {
    setPageStatus(statusFilter);
    setPage(1);
  }
  const [courtNames, setCourtNames] = useState<Record<number, string>>({});
  const [statusCounts, setStatusCounts] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<LoadFailure | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function fetchFilings() {
      setLoading(true);
      setError(null);
      try {
        const result = await listFilings({
          status: statusFilter || undefined,
          page,
        }, controller.signal);
        if (controller.signal.aborted) return;
        setFilings(result.filings);
        setTotal(result.total);
        setCourtNames(result.court_names);
        setStatusCounts(result.status_counts);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(loadFailure(err, "We couldn't load your filings. Please retry."));
        setFilings([]);
        setTotal(0);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    fetchFilings();
    return () => controller.abort();
  }, [statusFilter, page, reloadKey]);

  const countOf = (status: string) => statusCounts ? ` (${statusCounts[status] ?? 0})` : '';
  const allCount = statusCounts ? ` (${Object.values(statusCounts).reduce((sum, count) => sum + count, 0)})` : '';

  return (
    <div className="my-filings">
      <div className="page-header">
        <PageHeading>My filings</PageHeading>
        <Link to="/filing/new" className="btn btn-primary">New filing</Link>
      </div>

      {/* Filters */}
      <div className="filings-controls">
        <div className="form-group">
          <label htmlFor="filingStatus">Filter by status</label>
          <select id="filingStatus" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses{allCount}</option>
            {STATUSES.map(status => (
              <option key={status} value={status}>{FILING_STATUS_LABELS[status]}{countOf(status)}</option>
            ))}
          </select>
        </div>
        {!error && <span className="results-count">{plural(total, 'filing')}</span>}
      </div>

      {loading && <p className="loading">Loading filings...</p>}
      {error && <LoadError failure={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {!loading && !error && filings.length === 0 && (
        <div className="empty-state">
          <h2>No filings found</h2>
          <p>
            {statusFilter
              ? 'No filings match the selected filter.'
              : 'You haven\'t filed anything yet.'}
          </p>
          <Link to="/filing/new" className="btn btn-primary">Create Your First Filing</Link>
        </div>
      )}

      {!loading && filings.length > 0 && (
        <div className="filings-list">
          {filings.map((filing) => {
            return (
              <div key={filing.id} className="filing-card">
                <div className="filing-card-header">
                  <span className="filing-card-id">#{filing.id}</span>
                  <span className={`status-badge ${filing.status}`}>{filingStatusLabel(filing.status)}</span>
                </div>
                <h2 className="filing-card-title">{filing.case_title || 'Untitled Filing'}</h2>
                <div className="filing-card-meta">
                  <span>{courtNames[filing.court_id] || `Court #${filing.court_id}`}</span>
                  <span>{plural(filing.document_count, 'document')}</span>
                  <span>{formatDateTime(filing.submitted_at || filing.created_at)}</span>
                </div>
                {filing.rejection_reason && (
                  <div className="filing-card-reason">
                    <strong>Reason:</strong> {filing.rejection_reason}
                  </div>
                )}
                <div className="filing-card-actions">
                  {filing.status === 'draft' && (
                    <button className="btn btn-primary btn-small" onClick={() => navigate(`/filing/new?filing_id=${filing.id}`)}>Continue Filing</button>
                  )}
                  {filing.status === 'returned' && (
                    <button className="btn btn-primary btn-small" onClick={() => navigate(`/filing/new?filing_id=${filing.id}`)}>Resubmit</button>
                  )}
                  {filing.case_id ? (
                    <button className="btn btn-secondary btn-small" onClick={() => navigate(`/cases/${filing.case_id}`)}>View Case</button>
                  ) : (
                    <button className="btn btn-secondary btn-small" onClick={() => navigate(`/filing/new?filing_id=${filing.id}`)}>View Filing</button>
                  )}
                  {filing.submitted_at && <Link className="btn btn-secondary btn-small" to={`/filings/${filing.id}/history`}>Receipts &amp; history</Link>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {total > 25 && (
        <div className="pagination">
          <button
            className="btn btn-secondary btn-small"
            disabled={page <= 1 || loading}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <span>Page {page} of {Math.ceil(total / 25)}</span>
          <button
            className="btn btn-secondary btn-small"
            disabled={page >= Math.ceil(total / 25) || loading}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

export default MyFilings;
