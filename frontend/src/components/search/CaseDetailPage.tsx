import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { addFavorite, removeFavorite, listFavorites } from '../../api/favorites';

interface CaseDetail {
  id: number;
  court_id: number;
  case_number: string;
  case_type_id: number;
  title: string;
  status: string;
  filed_date: string;
  judge_id: number | null;
  participants: Array<{
    id: number;
    party_name: string;
    role: string;
    attorney_bar_number: string | null;
    contact_email: string | null;
  }>;
  created_at: string;
}

interface CaseFiling {
  id: number;
  status: string;
  case_title: string | null;
  filing_description: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  documents: Array<{
    id: number;
    document_type_code: string;
    title: string;
    file_size_bytes: number;
    page_count: number | null;
    mime_type: string;
  }>;
  created_at: string;
}

function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [caseData, setCaseData] = useState<CaseDetail | null>(null);
  const [filings, setFilings] = useState<CaseFiling[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFavorited, setIsFavorited] = useState(false);
  const [togglingFav, setTogglingFav] = useState(false);
  const [courtName, setCourtName] = useState('');

  useEffect(() => {
    async function load() {
      try {
        const [caseRes, filingsRes, favsRes] = await Promise.all([
          apiClient.get(`/cases/${caseId}`),
          apiClient.get(`/cases/${caseId}/filings`),
          listFavorites().catch(() => ({ favorites: [] })),
        ]);
        setCaseData(caseRes.data);
        setFilings(filingsRes.data);
        // Fetch court name
        try {
          const courtRes = await apiClient.get(`/courts/${caseRes.data.court_id}`);
          setCourtName(courtRes.data.name);
        } catch {
          setCourtName(`Court #${caseRes.data.court_id}`);
        }
        setIsFavorited(favsRes.favorites.some((f: { case_id: number }) => f.case_id === Number(caseId)));
      } catch {
        setError('Failed to load case details.');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [caseId]);

  const toggleFavorite = async () => {
    if (!caseData) return;
    setTogglingFav(true);
    try {
      if (isFavorited) {
        await removeFavorite(caseData.id);
        setIsFavorited(false);
      } else {
        await addFavorite(caseData.id);
        setIsFavorited(true);
      }
    } catch { /* ignore */ }
    finally { setTogglingFav(false); }
  };

  const formatDate = (d: string | null) => {
    if (!d) return '--';
    return new Date(d).toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  const roleLabel = (role: string) => {
    const map: Record<string, string> = {
      plaintiff: 'Plaintiff',
      defendant: 'Defendant',
      petitioner: 'Petitioner',
      respondent: 'Respondent',
      attorney_plaintiff: 'Attorney (Plaintiff)',
      attorney_defendant: 'Attorney (Defendant)',
      guardian: 'Guardian',
      intervenor: 'Intervenor',
    };
    return map[role] || role;
  };

  if (loading) return <div className="loading">Loading case...</div>;
  if (error || !caseData) return <div className="alert alert-error">{error || 'Case not found.'}</div>;

  return (
    <div className="case-detail-page">
      {/* Case Header */}
      <div className="case-detail-header">
        <div>
          <div className="case-detail-number">{caseData.case_number}</div>
          <h2>{caseData.title}</h2>
        </div>
        <div className="case-detail-actions">
          <button
            className={`fav-btn-large ${isFavorited ? 'favorited' : ''}`}
            onClick={toggleFavorite}
            disabled={togglingFav}
            title={isFavorited ? 'Remove from favorites' : 'Add to favorites'}
          >
            {isFavorited ? '\u2605 Favorited' : '\u2606 Favorite'}
          </button>
          <Link
            to={`/filing/new?case_id=${caseData.id}&court_id=${caseData.court_id}&case_type_id=${caseData.case_type_id}&case_title=${encodeURIComponent(caseData.title)}`}
            className="btn btn-primary"
          >
            File with Court
          </Link>
          <Link
            to={`/filing/new?case_id=${caseData.id}&court_id=${caseData.court_id}&case_type_id=${caseData.case_type_id}&case_title=${encodeURIComponent(caseData.title)}&service_only=true`}
            className="btn btn-secondary"
          >
            Serve Documents Only
          </Link>
        </div>
      </div>

      {/* Case Info */}
      <div className="case-detail-grid">
        <div className="case-detail-card">
          <h3>Case Information</h3>
          <div className="detail-grid">
            <div><label>Case Number</label><span>{caseData.case_number}</span></div>
            <div><label>Status</label><span className={`status-badge ${caseData.status}`}>{caseData.status}</span></div>
            <div><label>Court</label><span>{courtName}</span></div>
            <div><label>Filed Date</label><span>{formatDate(caseData.filed_date)}</span></div>
          </div>
        </div>

        {/* Parties */}
        <div className="case-detail-card">
          <h3>Parties ({caseData.participants.length})</h3>
          <div className="parties-list">
            {caseData.participants.map((p) => (
              <div key={p.id} className="party-item">
                <div className="party-role">{roleLabel(p.role)}</div>
                <div className="party-name">{p.party_name}</div>
                {p.attorney_bar_number && (
                  <div className="party-meta">Bar #: {p.attorney_bar_number}</div>
                )}
                {p.contact_email && (
                  <div className="party-meta">{p.contact_email}</div>
                )}
              </div>
            ))}
            {caseData.participants.length === 0 && (
              <p className="info-text">No parties on record.</p>
            )}
          </div>
        </div>
      </div>

      {/* Filing History / Docket */}
      <div className="case-detail-card">
        <div className="docket-header">
          <h3>Docket / Filing History ({filings.length})</h3>
          <Link
            to={`/filing/new?case_id=${caseData.id}&court_id=${caseData.court_id}&case_type_id=${caseData.case_type_id}&case_title=${encodeURIComponent(caseData.title)}`}
            className="btn btn-primary btn-small"
          >
            + Create New Filing
          </Link>
        </div>

        {filings.length > 0 ? (
          <div className="docket-list">
            {filings.map((f) => (
              <div key={f.id} className="docket-entry">
                <div className="docket-entry-header">
                  <span className="docket-entry-id">#{f.id}</span>
                  <span className={`status-badge ${f.status}`}>{f.status.replace('_', ' ')}</span>
                  <span className="docket-entry-date">{formatDate(f.submitted_at || f.created_at)}</span>
                </div>
                <div className="docket-entry-desc">
                  {f.filing_description || 'No description'}
                </div>
                {f.rejection_reason && (
                  <div className="docket-entry-reason">
                    <strong>Clerk note:</strong> {f.rejection_reason}
                  </div>
                )}
                <div className="docket-entry-docs">
                  {f.documents.map((doc) => (
                    <span key={doc.id} className="docket-doc">
                      {doc.title} ({doc.document_type_code}, {formatSize(doc.file_size_bytes)}
                      {doc.page_count ? `, ${doc.page_count}p` : ''})
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="info-text">No filings on record.</p>
        )}
      </div>
    </div>
  );
}

export default CaseDetailPage;
