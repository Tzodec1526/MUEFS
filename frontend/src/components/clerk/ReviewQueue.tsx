import { useState, useEffect } from 'react';
import { getClerkQueue, reviewFiling, FilingEnvelope } from '../../api/filings';

function ReviewQueue() {
  const [courtId, setCourtId] = useState(1);
  const [filings, setFilings] = useState<FilingEnvelope[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedFiling, setSelectedFiling] = useState<FilingEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [reviewReason, setReviewReason] = useState('');

  useEffect(() => {
    fetchQueue();
  }, [courtId]);

  async function fetchQueue() {
    setLoading(true);
    try {
      const result = await getClerkQueue(courtId);
      setFilings(result.filings);
      setTotal(result.total);
    } catch {
      setFilings([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleReview(filingId: number, action: 'accept' | 'reject' | 'return') {
    try {
      await reviewFiling(filingId, action, action !== 'accept' ? reviewReason : undefined);
      setSelectedFiling(null);
      setReviewReason('');
      fetchQueue();
    } catch (err) {
      console.error('Review failed:', err);
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div className="clerk-review">
      <h2>Clerk Review Queue</h2>

      <div className="queue-controls">
        <div className="form-group">
          <label htmlFor="courtSelect">Court</label>
          <select
            id="courtSelect"
            value={courtId}
            onChange={(e) => setCourtId(Number(e.target.value))}
          >
            <option value={1}>3rd Circuit Court - Wayne County</option>
            <option value={2}>6th Circuit Court - Oakland County</option>
            <option value={3}>22nd Circuit Court - Washtenaw County</option>
          </select>
        </div>
        <button className="btn btn-secondary" onClick={fetchQueue}>
          Refresh
        </button>
        <span className="queue-count">{total} pending filing(s)</span>
      </div>

      {loading && <p>Loading queue...</p>}

      <div className="queue-layout">
        {/* Filing List */}
        <div className="queue-list">
          <table>
            <thead>
              <tr>
                <th>Filing #</th>
                <th>Case Title</th>
                <th>Submitted</th>
                <th>Documents</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filings.map((filing) => (
                <tr
                  key={filing.id}
                  className={selectedFiling?.id === filing.id ? 'selected' : ''}
                  onClick={() => setSelectedFiling(filing)}
                >
                  <td>#{filing.id}</td>
                  <td>{filing.case_title || 'Untitled'}</td>
                  <td>{formatDate(filing.submitted_at)}</td>
                  <td>{filing.documents.length}</td>
                  <td>
                    <span className={`status-badge ${filing.status}`}>
                      {filing.status}
                    </span>
                  </td>
                </tr>
              ))}
              {!loading && filings.length === 0 && (
                <tr>
                  <td colSpan={5}>No pending filings</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Filing Detail Panel */}
        {selectedFiling && (
          <div className="filing-detail-panel">
            <h3>Filing #{selectedFiling.id}</h3>

            <div className="detail-section">
              <h4>Case Information</h4>
              <p><strong>Title:</strong> {selectedFiling.case_title || 'N/A'}</p>
              <p><strong>Description:</strong> {selectedFiling.filing_description || 'N/A'}</p>
              <p><strong>Submitted:</strong> {formatDate(selectedFiling.submitted_at)}</p>
            </div>

            <div className="detail-section">
              <h4>Documents ({selectedFiling.documents.length})</h4>
              <ul>
                {selectedFiling.documents.map((doc) => (
                  <li key={doc.id}>
                    {doc.title} ({doc.document_type_code})
                    {!doc.is_text_searchable && doc.mime_type === 'application/pdf' && (
                      <span className="warning-badge">Not text-searchable</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            <div className="detail-section">
              <h4>Review Actions</h4>
              <div className="form-group">
                <label htmlFor="reviewReason">Reason (required for reject/return)</label>
                <textarea
                  id="reviewReason"
                  value={reviewReason}
                  onChange={(e) => setReviewReason(e.target.value)}
                  rows={3}
                  placeholder="Enter reason for rejection or return..."
                />
              </div>
              <div className="review-buttons">
                <button
                  className="btn btn-success"
                  onClick={() => handleReview(selectedFiling.id, 'accept')}
                >
                  Accept Filing
                </button>
                <button
                  className="btn btn-warning"
                  onClick={() => handleReview(selectedFiling.id, 'return')}
                  disabled={!reviewReason.trim()}
                >
                  Return for Correction
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => handleReview(selectedFiling.id, 'reject')}
                  disabled={!reviewReason.trim()}
                >
                  Reject Filing
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ReviewQueue;
