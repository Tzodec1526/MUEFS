import { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Link2 } from 'lucide-react';
import { apiClient, needsErrorMessage } from '../../api/client';
import { participantRoles, type CaseDocket } from '../../api/cases';
import { addFavorite, removeFavorite, listFavorites } from '../../api/favorites';
import { getCaseTypes } from '../../api/courts';
import { formatBytes, formatCourtDate, formatShortDate, getDocumentLabel } from '../../utils/format';
import { getDemoRole } from '../auth/LoginScreen';
import { useToast } from '../common/Toast';
import DocumentDownload from '../common/DocumentDownload';

interface CaseFiling {
  id: number;
  status: string;
  case_title: string | null;
  filing_description: string | null;
  submitted_at: string | null;
  filing_date: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  documents: Array<{
    id: number;
    copy_id?: number | null;
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
  const { pushToast } = useToast();
  // Read-only viewers: the signed-in 'public' role and anonymous guests (no role).
  const role = getDemoRole();
  const isPublicViewer = role === 'public' || !role;
  const isFiler = role === 'attorney' || role === 'srl';
  const [caseData, setCaseData] = useState<CaseDocket | null>(null);
  const [filings, setFilings] = useState<CaseFiling[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFavorited, setIsFavorited] = useState(false);
  const [togglingFav, setTogglingFav] = useState(false);
  const [courtName, setCourtName] = useState('');
  const [caseTypeName, setCaseTypeName] = useState('');
  const [docketPage, setDocketPage] = useState(1);
  const [hasMoreFilings, setHasMoreFilings] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [docketError, setDocketError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    requestRef.current = controller;
    async function load() {
      setLoading(true);
      setError(null);
      setDocketError(null);
      setLoadingMore(false);
      setDocketPage(1);
      setCaseTypeName('');
      try {
        const [caseRes, filingsRes, favsRes] = await Promise.all([
          apiClient.get(`/cases/${caseId}`, { signal: controller.signal }),
          apiClient.get(`/cases/${caseId}/filings`, { signal: controller.signal }),
          !isFiler
            ? Promise.resolve({ favorites: [] as { case_id: number }[] })
            : listFavorites().catch(() => ({ favorites: [] })),
        ]);
        if (controller.signal.aborted) return;
        setCaseData(caseRes.data);
        setFilings(filingsRes.data);
        setHasMoreFilings(filingsRes.data.length === 25);
        // Fetch court name + case type label for a credible docket header
        try {
          const [courtRes, types] = await Promise.all([
            apiClient.get(`/courts/${caseRes.data.court_id}`, { signal: controller.signal }),
            // Include types the court has closed to new cases: existing dockets still carry them.
            getCaseTypes(caseRes.data.court_id, true),
          ]);
          if (controller.signal.aborted) return;
          setCourtName(courtRes.data.name);
          const ct = types.find((t) => t.id === caseRes.data.case_type_id);
          if (ct) setCaseTypeName(ct.name);
        } catch {
          if (controller.signal.aborted) return;
          setCourtName(`Court #${caseRes.data.court_id}`);
        }
        setIsFavorited(favsRes.favorites.some((f: { case_id: number }) => f.case_id === Number(caseId)));
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 403) {
          setError('This case is sealed or confidential and is not available for public viewing.');
        } else if (status === 404) {
          setError('Case not found.');
        } else {
          setError('Failed to load case details.');
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [caseId, isFiler]);

  const loadMoreFilings = async () => {
    const signal = requestRef.current?.signal;
    setLoadingMore(true);
    setDocketError(null);
    try {
      const { data } = await apiClient.get<CaseFiling[]>(`/cases/${caseId}/filings`, {
        params: { page: docketPage + 1 }, signal,
      });
      if (signal?.aborted) return;
      setFilings((previous) => [...previous, ...data]);
      setDocketPage((previous) => previous + 1);
      setHasMoreFilings(data.length === 25);
    } catch {
      if (!signal?.aborted) setDocketError('Could not load more filings. Please try again.');
    } finally {
      if (!signal?.aborted) setLoadingMore(false);
    }
  };

  const copyShareLink = async () => {
    const url = `${window.location.origin}/cases/${caseId}`;
    try {
      await navigator.clipboard.writeText(url);
      pushToast('Case link copied to clipboard', 'success');
    } catch {
      pushToast('Could not copy link', 'error');
    }
  };

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
    } catch (err) {
      if (needsErrorMessage(err)) pushToast('Could not update favorite', 'error');
    } finally { setTogglingFav(false); }
  };

  // Public dockets show register-of-actions language, not the internal e-filing
  // review pipeline. Filers and court staff see the true status.
  const docketStatus = (status: string): { label: string; cls: string } => {
    if (!isPublicViewer) return { label: status.replace('_', ' '), cls: status };
    switch (status) {
      case 'accepted': return { label: 'Filed', cls: 'accepted' };
      case 'served': return { label: 'Service documents recorded', cls: 'pending' };
      case 'returned':
      case 'rejected': return { label: 'Returned for correction', cls: 'returned' };
      default: return { label: 'Submitted', cls: 'submitted' };
    }
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
            type="button"
            className="btn btn-secondary btn-icon"
            onClick={copyShareLink}
            title="Copy shareable case link"
          >
            <Link2 size={16} aria-hidden="true" />
            <span className="sr-only">Copy shareable case link</span>
          </button>
          {caseData.can_manage_records && <Link to={`/cases/${caseData.id}/participants`} className="btn btn-secondary">Manage case access</Link>}
          {isFiler && (
            <button
              className={`fav-btn-large ${isFavorited ? 'favorited' : ''}`}
              onClick={toggleFavorite}
              disabled={togglingFav}
              title={isFavorited ? 'Remove from favorites' : 'Add to favorites'}
            >
              {isFavorited ? '\u2605 Favorited' : '\u2606 Favorite'}
            </button>
          )}
          {isFiler && caseData.can_file && (
            <>
              <Link
                to={`/filing/new?case_id=${caseData.id}&court_id=${caseData.court_id}&case_type_id=${caseData.case_type_id}`}
                className="btn btn-primary"
              >
                File with Court
              </Link>
              <Link
                to={`/filing/new?case_id=${caseData.id}&court_id=${caseData.court_id}&case_type_id=${caseData.case_type_id}&service_only=true`}
                className="btn btn-secondary"
              >
                Serve Documents Only
              </Link>
            </>
          )}
        </div>
      </div>

      {isFiler && !caseData.can_file && <p className="alert alert-info" role="status">
        Court-reviewed case participation is required to file documents in this case.
        Contact the court to confirm your access.
      </p>}

      {/* Case Info */}
      <div className="case-detail-grid">
        <div className="case-detail-card">
          <h3>Case Information</h3>
          <div className="detail-grid">
            <div><label>Case Number</label><span>{caseData.case_number}</span></div>
            <div><label>Case Type</label><span>{caseTypeName || '--'}</span></div>
            <div><label>Status</label><span className={`status-badge ${caseData.status}`}>{caseData.status}</span></div>
            <div><label>Court</label><span>{courtName}</span></div>
            <div><label>Filing Date</label><span>{formatCourtDate(caseData.filing_date)}</span></div>
            {!caseData.filing_date && <div><label>Stored date (not calendar-verified)</label><span>{formatShortDate(caseData.filed_date)}</span></div>}
          </div>
        </div>

        {/* Parties */}
        <div className="case-detail-card">
          <h3>Participants ({caseData.participants.length})</h3>
          <div className="parties-list">
            {caseData.participants.map((p) => (
              <div key={p.id} className="party-item">
                <div className="party-role">{participantRoles[p.role] || p.role}{!p.is_active && ' · Former'}</div>
                <div className="party-name">{p.party_name}</div>
                {p.represented_party_name && <div className="party-meta">Represents {p.represented_party_name}</div>}
                {p.attorney_bar_number && (
                  <div className="party-meta">Bar #: {p.attorney_bar_number}</div>
                )}
              </div>
            ))}
            {caseData.participants.length === 0 && (
              <p className="info-text">No participants on record.</p>
            )}
          </div>
        </div>
      </div>

      {/* Filing History / Docket */}
      <div className="case-detail-card">
        <div className="docket-header">
          <h3>Docket / Filing History ({filings.length})</h3>
          {isFiler && caseData.can_file && (
            <Link
              to={`/filing/new?case_id=${caseData.id}&court_id=${caseData.court_id}&case_type_id=${caseData.case_type_id}`}
              className="btn btn-primary btn-small"
            >
              + Create New Filing
            </Link>
          )}
        </div>

        {filings.length > 0 ? (
          <div className="docket-list">
            {filings.map((f) => (
              <div key={f.id} className="docket-entry">
                <div className="docket-entry-header">
                  <span className="docket-entry-id">#{f.id}</span>
                  {caseData.can_manage_records && <Link to={`/filings/${f.id}/history`}>Receipts &amp; history</Link>}
                  <span className={`status-badge ${docketStatus(f.status).cls}`}>{docketStatus(f.status).label}</span>
                  <span className="docket-entry-date">{f.filing_date
                    ? `Filing date: ${formatCourtDate(f.filing_date)}`
                    : f.submitted_at ? `Received: ${formatShortDate(f.submitted_at)}`
                      : `Created: ${formatShortDate(f.created_at)}`}</span>
                </div>
                <div className="docket-entry-desc">
                  {f.filing_description || 'No description'}
                </div>
                {!isPublicViewer && f.rejection_reason && (
                  <div className="docket-entry-reason">
                    <strong>Clerk note:</strong> {f.rejection_reason}
                  </div>
                )}
                <div className="docket-entry-docs">
                  {f.documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="docket-doc"
                    >
                      {doc.title} ({getDocumentLabel(doc.document_type_code)}, {formatBytes(doc.file_size_bytes)}
                      {doc.page_count ? `, ${doc.page_count}p` : ''})
                      <DocumentDownload id={doc.id} copyId={doc.copy_id ?? undefined} title={doc.title} />
                      {caseData.can_manage_records && <Link to={`/documents/${doc.id}/publication`}>Manage public access</Link>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="info-text">No filings on record.</p>
        )}
        {docketError && <p className="alert alert-error" role="alert">{docketError}</p>}
        {hasMoreFilings && (
          <button className="btn btn-secondary" onClick={loadMoreFilings} disabled={loadingMore}>
            {loadingMore ? 'Loading filings...' : 'Load more filings'}
          </button>
        )}
      </div>
    </div>
  );
}

export default CaseDetailPage;
