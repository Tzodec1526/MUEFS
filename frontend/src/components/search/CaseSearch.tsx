import { useState, useEffect, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Link2 } from 'lucide-react';
import { searchCases } from '../../api/cases';
import { listFavorites, addFavorite, removeFavorite } from '../../api/favorites';
import { getDemoRole } from '../auth/LoginScreen';
import LoadError from '../common/LoadError';
import { useToast } from '../common/Toast';
import { parseServerDate } from '../../utils/format';
import { logAgentActivity } from '../../webmcp/activity';

interface CaseResult {
  id: number;
  case_number: string;
  title: string;
  status: string;
  court_id: number;
  filed_date: string;
  participants: Array<{
    party_name: string;
    role: string;
    attorney_bar_number?: string | null;
  }>;
}

function CaseSearch() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { pushToast } = useToast();
  const demoRole = getDemoRole();
  const showFavorites = demoRole === 'attorney' || demoRole === 'srl';

  const initialParty = searchParams.get('party') || '';
  const initialCase = searchParams.get('case') || '';
  const initialPage = Math.max(1, parseInt(searchParams.get('page') || '1', 10) || 1);
  const urlDrivenSearch = Boolean(initialParty || initialCase);

  const [caseNumber, setCaseNumber] = useState(initialCase);
  const [partyName, setPartyName] = useState(initialParty);
  const [results, setResults] = useState<CaseResult[]>([]);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(urlDrivenSearch);
  const [favoritedIds, setFavoritedIds] = useState<Set<number>>(new Set());
  const [togglingFav, setTogglingFav] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(initialPage);

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

  const syncUrl = useCallback(
    (opts: { num: string; party: string; page: number }) => {
      const next = new URLSearchParams();
      if (opts.party) next.set('party', opts.party);
      if (opts.num) next.set('case', opts.num);
      if (opts.page > 1) next.set('page', String(opts.page));
      setSearchParams(next, { replace: true });
    },
    [setSearchParams],
  );

  const runSearch = useCallback(
    async (opts: { num: string; party: string; page: number; searched: boolean }) => {
      setSearching(true);
      setError(null);
      try {
        const data = await searchCases({
          case_number: opts.num || undefined,
          party_name: opts.party || undefined,
          page: opts.page,
        });
        setResults(data.cases);
        setTotal(data.total);
        setHasSearched(opts.searched);
        syncUrl(opts);
      } catch {
        setError("We couldn't reach the records system. Please try again.");
        setResults([]);
        setTotal(0);
      } finally {
        setSearching(false);
      }
    },
    [syncUrl],
  );

  useEffect(() => {
    // Initial load from URL params or recent filings list
    // eslint-disable-next-line react-hooks/set-state-in-effect
    runSearch({
      num: initialCase,
      party: initialParty,
      page: initialPage,
      searched: urlDrivenSearch,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = () => {
    setPage(1);
    runSearch({ num: caseNumber, party: partyName, page: 1, searched: true });
  };

  const goToPage = (p: number) => {
    setPage(p);
    runSearch({ num: caseNumber, party: partyName, page: p, searched: hasSearched });
  };

  const copyShareLink = async () => {
    const params = new URLSearchParams();
    if (partyName) params.set('party', partyName);
    if (caseNumber) params.set('case', caseNumber);
    if (page > 1) params.set('page', String(page));
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
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
        tooldescription="Search Michigan public court records by party name and case number"
        onSubmit={(e) => {
          e.preventDefault();
          logAgentActivity(
            'search_cases',
            { case_number: caseNumber, party_name: partyName, via: 'declarative_form' },
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
              onKeyDown={handleKeyDown}
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
              onKeyDown={handleKeyDown}
              placeholder="e.g., Smith"
              toolparamdescription="Party or litigant name"
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={searching}>
            {searching ? 'Searching...' : 'Search'}
          </button>
          {(hasSearched || partyName || caseNumber) && (
            <button
              type="button"
              className="btn btn-secondary btn-icon"
              onClick={copyShareLink}
              title="Copy shareable link"
            >
              <Link2 size={16} aria-hidden="true" />
              <span className="sr-only">Copy shareable link</span>
            </button>
          )}
        </div>
      </form>

      {error ? (
        <LoadError message={error} onRetry={() => goToPage(page)} />
      ) : (
        <div className="search-results">
          <h3>{hasSearched ? `Results (${total})` : 'Recent public filings'}</h3>
          {results.length > 0 ? (
            <table>
              <thead>
                <tr>
                  {showFavorites && <th className="th-fav"></th>}
                  <th>Case Number</th>
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
                    <td>{c.title}</td>
                    <td>
                      <span className={`status-badge ${c.status}`}>{c.status}</span>
                    </td>
                    <td>{parseServerDate(c.filed_date).toLocaleDateString()}</td>
                    <td>
                      {c.participants.map((p) => `${p.party_name} (${p.role})`).join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
