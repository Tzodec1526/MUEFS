import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { listFilings, FilingSummary } from '../../api/filings';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import { FILING_STATUS_LABELS, filingStatusLabel } from '../../utils/filingStatus';
import { parseServerDate } from '../../utils/format';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'draft', label: 'Drafts' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'under_review', label: 'Under review' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'returned', label: 'Returned' },
  { value: 'served', label: 'Service documents recorded' },
];

function MyFilings() {
  usePageTitle('My filings');
  const navigate = useNavigate();
  const [filings, setFilings] = useState<FilingSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedStatus = searchParams.get('status') ?? '';
  const statusFilter = STATUS_OPTIONS.some(option => option.value === requestedStatus) ? requestedStatus : '';
  const setStatusFilter = (status: string) => setSearchParams(status ? { status } : {}, { replace: true });
  const [paged, setPaged] = useState({ status: statusFilter, page: 1 });
  const page = paged.status === statusFilter ? paged.page : 1;
  const setPage = (next: number) => setPaged({ status: statusFilter, page: next });
  const [courtNames, setCourtNames] = useState<Record<number, string>>({});
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
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

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '--';
    return parseServerDate(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="my-filings">
      <div className="page-header">
        <PageHeading>My Filings</PageHeading>
        <Link to="/filing/new" className="btn btn-primary">New Filing</Link>
      </div>

      {/* Status summary cards */}
      <div className="status-summary">
        {Object.entries(FILING_STATUS_LABELS).map(([s, label]) => {
          return (
            <button
              key={s}
              className={`status-card ${statusFilter === s ? 'active' : ''}`}
              onClick={() => setStatusFilter(statusFilter === s ? '' : s)}
            >
              <span className="status-card-count">{statusCounts[s] || 0}</span>
              <span className={`status-badge ${s}`}>{label}</span>
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div className="filings-controls">
        <div className="form-group">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by status"
          >
            {STATUS_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <span className="results-count">{total} filing(s)</span>
      </div>

      {loading && <p className="loading">Loading filings...</p>}
      {error && <LoadError failure={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {!loading && !error && filings.length === 0 && (
        <div className="empty-state">
          <h3>No filings found</h3>
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
                <h4 className="filing-card-title">{filing.case_title || 'Untitled Filing'}</h4>
                <div className="filing-card-meta">
                  <span>{courtNames[filing.court_id] || `Court #${filing.court_id}`}</span>
                  <span>{filing.document_count} document(s)</span>
                  <span>{formatDate(filing.submitted_at || filing.created_at)}</span>
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
                    <button className="btn btn-warning btn-small" onClick={() => navigate(`/filing/new?filing_id=${filing.id}`)}>Resubmit</button>
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
