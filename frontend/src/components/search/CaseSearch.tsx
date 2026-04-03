import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { searchCases } from '../../api/cases';
import { listFavorites, addFavorite, removeFavorite } from '../../api/favorites';

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
  }>;
}

function CaseSearch() {
  const [caseNumber, setCaseNumber] = useState('');
  const [partyName, setPartyName] = useState('');
  const [results, setResults] = useState<CaseResult[]>([]);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [favoritedIds, setFavoritedIds] = useState<Set<number>>(new Set());
  const [togglingFav, setTogglingFav] = useState<number | null>(null);

  // Load user's favorites on mount
  useEffect(() => {
    async function loadFavorites() {
      try {
        const data = await listFavorites();
        setFavoritedIds(new Set(data.favorites.map(f => f.case_id)));
      } catch {
        // API not available or not authenticated
      }
    }
    loadFavorites();
  }, []);

  const handleSearch = async () => {
    setSearching(true);
    setHasSearched(true);
    try {
      const data = await searchCases({
        case_number: caseNumber || undefined,
        party_name: partyName || undefined,
      });
      setResults(data.cases);
      setTotal(data.total);
    } catch {
      setResults([]);
      setTotal(0);
    } finally {
      setSearching(false);
    }
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
        Search for cases across all Michigan courts. You can search by case number
        or party name. Click the star to add a case to your favorites.
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
              placeholder="e.g., MI-1-2024-000001"
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

      {hasSearched && (
        <div className="search-results">
          <h3>Results ({total})</h3>
          {results.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th className="th-fav"></th>
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
            <p>No cases found matching your search criteria.</p>
          )}
        </div>
      )}
    </div>
  );
}

export default CaseSearch;
