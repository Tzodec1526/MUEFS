import { useState } from 'react';
import { Link } from 'react-router-dom';
import { searchCases } from '../../api/cases';
import { logAgentActivity } from '../../webmcp/activity';
import { useToast } from '../common/Toast';

type Hit = {
  id: number;
  case_number: string;
  title: string;
};

/** Declarative search_cases form on the agent hub. */
function AgentDeclarativeSearch() {
  const { pushToast } = useToast();
  const [partyName, setPartyName] = useState('Smith');
  const [caseNumber, setCaseNumber] = useState('');
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<Hit[]>([]);

  const runSearch = async () => {
    setSearching(true);
    try {
      const data = await searchCases({
        party_name: partyName || undefined,
        case_number: caseNumber || undefined,
        page: 1,
      });
      const next = (data.cases ?? []).slice(0, 5).map((c: { id: number; case_number: string; title: string }) => ({
        id: c.id,
        case_number: c.case_number,
        title: c.title,
      }));
      setHits(next);
      logAgentActivity(
        'search_cases',
        {
          party_name: partyName,
          case_number: caseNumber,
          via: 'declarative_form',
          surface: 'agent_hub',
        },
        true,
        0,
      );
      pushToast(next.length ? `Found ${data.total}` : 'No matches', next.length ? 'success' : 'error');
    } catch (err) {
      logAgentActivity(
        'search_cases',
        { party_name: partyName, case_number: caseNumber, via: 'declarative_form' },
        false,
        0,
      );
      pushToast(err instanceof Error ? err.message : 'Search failed', 'error');
    } finally {
      setSearching(false);
    }
  };

  return (
    <section className="agent-hub-declarative">
      <h2>Case search</h2>
      <form
        className="agent-declarative-form"
        toolname="search_cases"
        tooldescription="Search Michigan public court records by party name and case number"
        onSubmit={(e) => {
          e.preventDefault();
          void runSearch();
        }}
      >
        <div className="form-group">
          <label htmlFor="agentHubParty">Party name</label>
          <input
            id="agentHubParty"
            name="party_name"
            type="text"
            value={partyName}
            onChange={(e) => setPartyName(e.target.value)}
            placeholder="Smith"
            toolparamdescription="Party or litigant name"
          />
        </div>
        <div className="form-group">
          <label htmlFor="agentHubCase">Case number</label>
          <input
            id="agentHubCase"
            name="case_number"
            type="text"
            value={caseNumber}
            onChange={(e) => setCaseNumber(e.target.value)}
            placeholder="optional"
            toolparamdescription="Case number (partial match)"
          />
        </div>
        <button className="btn btn-primary" type="submit" disabled={searching}>
          {searching ? 'Searching…' : 'Search'}
        </button>
      </form>
      {hits.length > 0 && (
        <ul className="agent-declarative-hits">
          {hits.map((h) => (
            <li key={h.id}>
              <code>{h.case_number}</code> {h.title}{' '}
              <Link to={`/cases/${h.id}`}>Open</Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default AgentDeclarativeSearch;
