import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { searchCases } from '../../api/cases';
import { listFavorites, addFavorite, removeFavorite } from '../../api/favorites';
import { getDemoRole } from '../auth/LoginScreen';
import LoadError from '../common/LoadError';

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
  const demoRole = getDemoRole();
  // Favorites require a signed-in filer; guests (no role) and public viewers browse read-only.
  const showFavorites = demoRole === 'attorney' || demoRole === 'srl';
  const [caseNumber, setCaseNumber] = useState('');
  const [partyName, setPartyName] = useState('');
  const [results, setResults] = useState<CaseResult[]>([]);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [favoritedIds, setFavoritedIds] = useState<Set<number>>(new Set());
  const [togglingFav, setTogglingFav] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  // Load user's favorites on mount (filers and counsel only)
  useEffect(() => {
    if (!showFavorites) return;
    async function loadFavorites() {
      try {
        const data = await listFavorites();
        setFavoritedIds(new Set(data.favorites.map(f => f.case_id)));
      } catch {
        // API not available or not authenticated
      }
    }
    loadFavorites();
  }, [showFavorites]);

  const runSearch = async (opts: { num: string; party: string; page: number; searched: boolean }) => {
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
    } catch {
      setError("We couldn't reach the records system. Please try again.");
      setResults([]);
      setTotal(0);
    } finally {
      setSearching(false);
    }
  };

  // Auto-load recent public filings on mount so an empty search isn't a dead end.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    runSearch({ num: '', party: '', page: 1, searched: false });
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

  const toggleFavorite = async (caseId: number) => {
    setTogglingFav(caseId);
    try {
      if (favoritedIds.has(caseId)) {
        await removeFavorite(caseId);
        setFavoritedIds(prev => {
          const next = new Set(prev);
          next.delete(caseId);
          return next;
        });
      } else {
        await addFavorite(caseId);
        setFavoritedIds(prev => new Set(prev).add(caseId));
      }
    } catch {
      // Silently fail - might not be authenticated
    } finally {
      setTogglingFav(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
  };

  return (
    <div className="case-search">
      <h2>Case Search</h2>
      <p className="info-text">
        Search non-sealed cases across Michigan courts by case number or party name &mdash; no account
        needed. Partial numbers and names work.
        {showFavorites ? ' Click the star to add a case to your favorites.' : ''}
      </p>

      <div className="search-form">
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="caseNum">Case Number</label>
            <input
              id="caseNum"
              type="text"
              value={caseNumber}
              onChange={(e) => setCaseNumber(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g., 25-000001-CZ"
            />
          </div>
          <div className="form-group">
            <label htmlFor="partyName">Party Name</label>
            <input
              id="partyName"
              type="text"
              value={partyName}
              onChange={(e) => setPartyName(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g., Smith"
            />
          </div>
          <button className="btn btn-primary" onClick={handleSearch} disabled={searching}>
            {searching ? 'Searching...' : 'Search'}
          </button>
        </div>
      </div>

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
                    <td>{new Date(c.filed_date).toLocaleDateString()}</td>
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
