import { useState } from 'react';
import { searchCases } from '../../api/documents';

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

  return (
    <div className="case-search">
      <h2>Case Search</h2>
      <p className="info-text">
        Search for cases across all Michigan courts. You can search by case number
        or party name.
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
                    <td><a href={`/cases/${c.id}`}>{c.case_number}</a></td>
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
