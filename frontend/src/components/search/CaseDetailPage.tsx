import { useState, useEffect, useRef, useContext } from 'react';
import { useParams, Link } from 'react-router-dom';
import { actionErrorMessage, apiClient } from '../../api/client';
import { participantRoles, type CaseDocket } from '../../api/cases';
import { addFavorite, removeFavorite, listFavorites } from '../../api/favorites';
import { getCaseTypes } from '../../api/courts';
import { getDocumentLabel } from '../../utils/documentTypes';
import { formatBytes, formatCourtDate, formatShortDate, plural } from '../../utils/format';
import { errorMessage } from '../../utils/errors';
import { CourtContext } from '../auth/CourtSession';
import { useToast } from '../common/Toast';
import DocumentDownload from '../common/DocumentDownload';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';
import PageLoadError from '../common/PageLoadError';

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
  const { role } = useContext(CourtContext)!;
  const isPublicViewer = role === 'public' || !role;
  const isFiler = role === 'attorney' || role === 'srl';
  const [caseData, setCaseData] = useState<CaseDocket | null>(null);
  const [filings, setFilings] = useState<CaseFiling[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ heading: string; message: string } | null>(null);
  usePageTitle(error?.heading ?? (caseData?.title || 'Case docket'));
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
            : listFavorites().catch((err: unknown) => {
              const message = !controller.signal.aborted && actionErrorMessage(err, 'Could not load your favorite cases.');
              if (message) pushToast(message, 'error');
              return { favorites: [] };
            }),
        ]);
        if (controller.signal.aborted) return;
        setCaseData(caseRes.data);
        setFilings(filingsRes.data);
        setHasMoreFilings(filingsRes.data.length === 25);
        // Fetch court name + case type label for a credible docket header
        const report = (err: unknown, fallback: string) => {
          const message = !controller.signal.aborted && actionErrorMessage(err, fallback);
          if (message) pushToast(message, 'error');
        };
        const [court, types] = await Promise.all([
          apiClient.get<{ name: string }>(`/courts/${caseRes.data.court_id}`, { signal: controller.signal })
            .then(({ data }) => data.name)
            .catch((err: unknown) => {
              report(err, "Could not load the court's name.");
              return `Court #${caseRes.data.court_id}`;
            }),
          // Include types the court has closed to new cases: existing dockets still carry them.
          getCaseTypes(caseRes.data.court_id, true).catch((err: unknown) => {
            report(err, 'Could not load the case type name.');
            return [];
          }),
        ]);
        if (controller.signal.aborted) return;
        setCourtName(court);
        const ct = types.find((t) => t.id === caseRes.data.case_type_id);
        if (ct) setCaseTypeName(ct.name);
        setIsFavorited(favsRes.favorites.some((f: { case_id: number }) => f.case_id === Number(caseId)));
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 403) {
          setError({ heading: 'Case not available', message: 'This case is sealed or confidential and is not available for public viewing.' });
        } else if (status === 404) {
          setError({ heading: 'Case not found', message: 'Case not found.' });
        } else {
          setError({ heading: 'Case not loaded', message: errorMessage(err, 'Failed to load case details.') });
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [caseId, isFiler, pushToast]);

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
    } catch (err) {
      if (!signal?.aborted) setDocketError(errorMessage(err, 'Could not load more filings. Please try again.'));
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
      const message = actionErrorMessage(err, 'Could not update favorite');
      if (message) pushToast(message, 'error');
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
  if (error || !caseData) {
    const failure = error ?? { heading: 'Case not found', message: 'Case not found.' };
    return <PageLoadError heading={failure.heading} failure={{ message: failure.message, retry: false }} />;
  }

  return (
    <div className="case-detail-page">
      {/* Case Header */}
      <div className="case-detail-header">
        <div>
          <PageHeading>{caseData.title}</PageHeading>
          <p className="case-detail-number">
            {caseData.case_number} <span className={`status-badge ${caseData.status}`}>{caseData.status}</span>
          </p>
        </div>
        <div className="case-detail-actions">
          <button type="button" className="btn btn-secondary" onClick={copyShareLink}>Copy link</button>
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
                File in this case
              </Link>
              <Link
                to={`/filing/new?case_id=${caseData.id}&court_id=${caseData.court_id}&case_type_id=${caseData.case_type_id}&service_only=true`}
                className="btn btn-secondary"
              >
                Serve documents only
              </Link>
            </>
          )}
        </div>
      </div>

      {isFiler && !caseData.can_file && <p className="alert alert-info">
        Court-reviewed case participation is required to file documents in this case.
        Contact the court to confirm your access.
      </p>}

      {/* Case Info */}
      <div className="case-detail-grid">
        <div className="case-detail-card">
          <h2>Case information</h2>
          <div className="detail-grid">
            <div><label>Case type</label><span>{caseTypeName || '--'}</span></div>
            <div><label>Court</label><span>{courtName}</span></div>
            <div><label>Filing date</label><span>{formatCourtDate(caseData.filing_date)}</span></div>
            {!caseData.filing_date && <div><label>Date on record (not yet confirmed by the court)</label><span>{formatShortDate(caseData.filed_date)}</span></div>}
          </div>
        </div>

        {/* Parties */}
        <div className="case-detail-card">
          <h2>Participants ({caseData.participants.length})</h2>
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
        <h2>Docket</h2>

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
                      <span>{doc.title} ({getDocumentLabel(doc.document_type_code)}, {formatBytes(doc.file_size_bytes)}
                        {doc.page_count ? `, ${plural(doc.page_count, 'page')}` : ''})</span>
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
