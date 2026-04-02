import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { listFilings, FilingEnvelope } from '../../api/filings';

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'draft', label: 'Drafts' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'under_review', label: 'Under Review' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'returned', label: 'Returned' },
];

function MyFilings() {
  const [filings, setFilings] = useState<FilingEnvelope[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  useEffect(() => {
    async function fetchFilings() {
      setLoading(true);
      try {
        const result = await listFilings({
          status: statusFilter || undefined,
          page,
        });
        setFilings(result.filings);
        setTotal(result.total);
      } catch {
        setFilings([]);
      } finally {
        setLoading(false);
      }
    }
    fetchFilings();
  }, [statusFilter, page]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '--';
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStatusInfo = (status: string) => {
    switch (status) {
      case 'draft': return { label: 'Draft', className: 'draft', action: 'Continue editing' };
      case 'submitted': return { label: 'Submitted', className: 'submitted', action: 'Awaiting review' };
      case 'under_review': return { label: 'Under Review', className: 'under_review', action: 'Being reviewed' };
      case 'accepted': return { label: 'Accepted', className: 'accepted', action: 'Filed with court' };
      case 'rejected': return { label: 'Rejected', className: 'rejected', action: 'See reason' };
      case 'returned': return { label: 'Returned', className: 'returned', action: 'Needs correction' };
      default: return { label: status, className: '', action: '' };
    }
  };

  const statusCounts = useMemo(() =>
    filings.reduce((acc, f) => {
      acc[f.status] = (acc[f.status] || 0) + 1;
      return acc;
    }, {} as Record<string, number>),
  [filings]);

  return (
    <div className="my-filings">
      <div className="page-header">
        <h2>My Filings</h2>
        <Link to="/filing/new" className="btn btn-primary">New Filing</Link>
      </div>

      {/* Status summary cards */}
      <div className="status-summary">
        {['draft', 'submitted', 'under_review', 'accepted', 'rejected', 'returned'].map(s => {
          const info = getStatusInfo(s);
          return (
            <button
              key={s}
              className={`status-card ${statusFilter === s ? 'active' : ''}`}
              onClick={() => setStatusFilter(statusFilter === s ? '' : s)}
            >
              <span className="status-card-count">{statusCounts[s] || 0}</span>
              <span className={`status-badge ${info.className}`}>{info.label}</span>
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div className="filings-controls">
        <div className="form-group">
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
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

      {!loading && filings.length === 0 && (
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
            const info = getStatusInfo(filing.status);
            return (
              <div key={filing.id} className="filing-card">
                <div className="filing-card-header">
                  <span className="filing-card-id">#{filing.id}</span>
                  <span className={`status-badge ${info.className}`}>{info.label}</span>
                </div>
                <h4 className="filing-card-title">{filing.case_title || 'Untitled Filing'}</h4>
                <div className="filing-card-meta">
                  <span>Court #{filing.court_id}</span>
                  <span>{filing.documents.length} document(s)</span>
                  <span>{formatDate(filing.submitted_at || filing.created_at)}</span>
                </div>
                {filing.rejection_reason && (
                  <div className="filing-card-reason">
                    <strong>Reason:</strong> {filing.rejection_reason}
                  </div>
                )}
                <div className="filing-card-actions">
                  {filing.status === 'draft' && (
                    <button className="btn btn-primary btn-small">Continue Filing</button>
                  )}
                  {filing.status === 'returned' && (
                    <button className="btn btn-warning btn-small">Resubmit</button>
                  )}
                  <button className="btn btn-secondary btn-small">View Details</button>
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
            disabled={page <= 1}
            onClick={() => setPage(p => p - 1)}
          >
            Previous
          </button>
          <span>Page {page} of {Math.ceil(total / 25)}</span>
          <button
            className="btn btn-secondary btn-small"
            disabled={page >= Math.ceil(total / 25)}
            onClick={() => setPage(p => p + 1)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

export default MyFilings;
