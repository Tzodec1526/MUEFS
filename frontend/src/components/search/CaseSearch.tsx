import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Link2 } from 'lucide-react';
import { CaseSearchResult, searchCases } from '../../api/cases';
import { CourtDirectoryEntry, listCourtDirectory } from '../../api/courts';
import { listFavorites, addFavorite, removeFavorite } from '../../api/favorites';
import { getDemoRole } from '../auth/LoginScreen';
import LoadError from '../common/LoadError';
import { useToast } from '../common/Toast';
import { formatCourtDate, parseServerDate } from '../../utils/format';
import { logAgentActivity } from '../../webmcp/activity';

function CaseSearch() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { pushToast } = useToast();
  const demoRole = getDemoRole();
  const showFavorites = demoRole === 'attorney' || demoRole === 'srl';

  const submittedPartyName = searchParams.get('party') || '';
  const submittedCaseNumber = searchParams.get('case') || '';
  const submittedCourt = searchParams.get('court') || '';
  const invalidCourt = Boolean(submittedCourt) && (!/^\d+$/.test(submittedCourt)
    || Number(submittedCourt) < 1 || Number(submittedCourt) > 2_147_483_647);
  const page = Math.max(1, parseInt(searchParams.get('page') || '1', 10) || 1);
  const hasSearched = Boolean(submittedPartyName || submittedCaseNumber || submittedCourt);

  const [caseNumber, setCaseNumber] = useState(submittedCaseNumber);
  const [partyName, setPartyName] = useState(submittedPartyName);
  const [courtId, setCourtId] = useState(submittedCourt);
  const [courts, setCourts] = useState<CourtDirectoryEntry[]>([]);
  const [courtError, setCourtError] = useState(false);
  const [courtReloadKey, setCourtReloadKey] = useState(0);
  const [results, setResults] = useState<CaseSearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [favoritedIds, setFavoritedIds] = useState<Set<number>>(new Set());
  const [togglingFav, setTogglingFav] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    listCourtDirectory(controller.signal).then(data => {
      if (!controller.signal.aborted) {
        setCourts(data);
        setCourtError(false);
      }
    }).catch(() => {
      if (!controller.signal.aborted) setCourtError(true);
    });
    return () => controller.abort();
  }, [courtReloadKey]);

  useEffect(() => {
    if (!showFavorites) return;
    async function loadFavorites() {
      try {
        const data = await listFavorites();
        setFavoritedIds(new Set(data.favorites.map((f) => f.case_id)));
      } catch {
        // not authenticated
      }
    }
    loadFavorites();
  }, [showFavorites]);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setSearching(true);
      setError(null);
      setCaseNumber(submittedCaseNumber);
      setPartyName(submittedPartyName);
      setCourtId(submittedCourt && !invalidCourt ? String(Number(submittedCourt)) : submittedCourt);
      if (invalidCourt) {
        setError('The court filter in this link is invalid. Choose a court and search again.');
        setResults([]);
        setTotal(0);
        setSearching(false);
        return;
      }
      try {
        const data = await searchCases({
          case_number: submittedCaseNumber || undefined,
          party_name: submittedPartyName || undefined,
          court_id: submittedCourt ? Number(submittedCourt) : undefined,
          page: page,
        }, controller.signal);
        if (controller.signal.aborted) return;
        setResults(data.cases);
        setTotal(data.total);
      } catch {
        if (controller.signal.aborted) return;
        setError("We couldn't reach the records system. Please try again.");
        setResults([]);
        setTotal(0);
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    }
    load();
    return () => controller.abort();
  }, [submittedCaseNumber, submittedPartyName, submittedCourt, invalidCourt, page, reloadKey]);

  const handleSearch = () => {
    const next = new URLSearchParams();
    if (caseNumber.trim()) next.set('case', caseNumber.trim());
    if (partyName.trim()) next.set('party', partyName.trim());
    if (courtId) next.set('court', courtId);
    if (next.toString() === searchParams.toString()) setReloadKey((key) => key + 1);
    else setSearchParams(next);
  };

  const goToPage = (p: number) => {
    const next = new URLSearchParams(searchParams);
    if (p > 1) next.set('page', String(p));
    else next.delete('page');
    setSearchParams(next);
  };

  const copyShareLink = async () => {
    const params = searchParams;
    const url = `${window.location.origin}/cases/search${params.toString() ? `?${params}` : ''}`;
    try {
      await navigator.clipboard.writeText(url);
      pushToast('Search link copied to clipboard', 'success');
    } catch {
      pushToast('Could not copy link', 'error');
    }
  };

  const toggleFavorite = async (caseId: number) => {
    setTogglingFav(caseId);
    try {
      if (favoritedIds.has(caseId)) {
        await removeFavorite(caseId);
        setFavoritedIds((prev) => {
          const next = new Set(prev);
          next.delete(caseId);
          return next;
        });
        pushToast('Removed from favorites', 'success');
      } else {
        await addFavorite(caseId);
        setFavoritedIds((prev) => new Set(prev).add(caseId));
        pushToast('Added to favorites', 'success');
      }
    } catch {
      pushToast('Could not update favorite', 'error');
    } finally {
      setTogglingFav(null);
    }
  };

  return (
    <div className="case-search">
      <div className="case-search-hero">
        <h2>Statewide case search</h2>
        <p className="info-text">
          One search across Michigan courts — no account, no vendor portal hopping. Sealed matters
          stay off the index. Partial names and case numbers work.
          {showFavorites ? ' Star cases to file motions faster.' : ''}
        </p>
      </div>

      <form
        className="search-form"
        toolname="search_cases"
        tooldescription="Search Michigan public court records by party name, case number and court"
        onSubmit={(e) => {
          e.preventDefault();
          logAgentActivity(
            'search_cases',
            { case_number: caseNumber, party_name: partyName, court_id: courtId, via: 'declarative_form' },
            true,
            0,
          );
          handleSearch();
        }}
      >
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="caseNum">Case Number</label>
            <input
              id="caseNum"
              name="case_number"
              type="text"
              value={caseNumber}
              onChange={(e) => setCaseNumber(e.target.value)}
              placeholder="e.g., 25-000001-CZ"
              toolparamdescription="Case number (partial match)"
            />
          </div>
          <div className="form-group">
            <label htmlFor="partyName">Party Name</label>
            <input
              id="partyName"
              name="party_name"
              type="text"
              value={partyName}
              onChange={(e) => setPartyName(e.target.value)}
              placeholder="e.g., Smith"
              toolparamdescription="Party or litigant name"
            />
          </div>
          <div className="form-group">
            <label htmlFor="searchCourt">Court</label>
            <select id="searchCourt" name="court_id" value={courtId}
              onChange={e => setCourtId(e.target.value)}
              toolparamdescription="Optional court ID; leave blank to search all courts">
              <option value="">All courts</option>
              {courtId && !courts.some(court => String(court.id) === courtId) && (
                <option value={courtId}>Selected court ({courtId})</option>
              )}
              {courts.map(court => (
                <option key={court.id} value={court.id}>{court.county} — {court.name}</option>
              ))}
            </select>
          </div>
          <button className="btn btn-primary" type="submit" disabled={searching}>
            {searching ? 'Searching...' : 'Search'}
          </button>
          {(hasSearched || page > 1) && (
            <button
              type="button"
              className="btn btn-secondary btn-icon"
              onClick={copyShareLink}
              title="Copy results link"
            >
              <Link2 size={16} aria-hidden="true" />
              <span className="sr-only">Copy results link</span>
            </button>
          )}
        </div>
      </form>

      {courtError && <LoadError message="We couldn't load the court list. Please retry."
        onRetry={() => setCourtReloadKey(key => key + 1)} />}

      {error ? (
        <LoadError message={error}
          onRetry={invalidCourt ? undefined : () => setReloadKey((key) => key + 1)} />
      ) : (
        <div className="search-results">
          <h3>{hasSearched ? `Results (${total})` : 'Recent public filings'}</h3>
          {results.length > 0 ? (
            <div className="case-search-table" role="region" aria-label="Case search results" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    {showFavorites && <th className="th-fav"></th>}
                    <th>Case Number</th>
                    <th>Court</th>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Filed Date</th>
                    <th>Parties</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((c) => (
                    <tr key={c.id}>
                      {showFavorites && (
                        <td className="td-fav">
                          <button
                            className={`fav-btn ${favoritedIds.has(c.id) ? 'favorited' : ''}`}
                            onClick={() => toggleFavorite(c.id)}
                            disabled={togglingFav === c.id}
                            title={favoritedIds.has(c.id) ? 'Remove from favorites' : 'Add to favorites'}
                            aria-label={favoritedIds.has(c.id) ? 'Remove from favorites' : 'Add to favorites'}
                          >
                            {favoritedIds.has(c.id) ? '\u2605' : '\u2606'}
                          </button>
                        </td>
                      )}
                      <td><Link to={`/cases/${c.id}`}>{c.case_number}</Link></td>
                      <td>{c.court_name}<br /><small>{c.court_county}</small></td>
                      <td>{c.title}</td>
                      <td>
                        <span className={`status-badge ${c.status}`}>{c.status}</span>
                      </td>
                      <td>{c.filing_date ? formatCourtDate(c.filing_date)
                        : `${parseServerDate(c.filed_date).toLocaleDateString()} (unverified)`}</td>
                      <td>
                        {c.participants.map((p) => `${p.party_name} (${p.role})`).join(', ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="info-text">
              {searching
                ? 'Searching…'
                : hasSearched
                  ? 'No cases found. Check the number or name — partial matches work.'
                  : 'No public filings to show yet.'}
            </p>
          )}
          {results.length > 0 && Math.ceil(total / 25) > 1 && (
            <div className="pagination">
              <button
                className="btn btn-secondary btn-small"
                disabled={page <= 1 || searching}
                onClick={() => goToPage(page - 1)}
              >
                Previous
              </button>
              <span>Page {page} of {Math.ceil(total / 25)}</span>
              <button
                className="btn btn-secondary btn-small"
                disabled={page >= Math.ceil(total / 25) || searching}
                onClick={() => goToPage(page + 1)}
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default CaseSearch;
