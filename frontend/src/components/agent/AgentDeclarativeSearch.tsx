import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { searchCases } from '../../api/cases';
import { trackAgentSubmission, type AgentSubmission } from '../../webmcp/declarative';
import { apiErrorResult, toolError } from '../../webmcp/output';
import { caseSearchResult } from '../../webmcp/records';
import { useToast } from '../common/Toast';

type Hit = {
  id: number;
  case_number: string;
  title: string;
};

/** The agent hub's declarative search form (search_cases_form; search_cases is the imperative tool). */
function AgentDeclarativeSearch() {
  const { pushToast } = useToast();
  const [partyName, setPartyName] = useState('Smith');
  const [caseNumber, setCaseNumber] = useState('');
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<Hit[]>([]);

  // reportAgent is set only for an agent-invoked submission; human searches are not agent activity.
  const runSearch = async (
    search: { party_name: string; case_number: string },
    reportAgent: AgentSubmission | null,
  ) => {
    setSearching(true);
    try {
      const data = await searchCases({
        party_name: search.party_name || undefined,
        case_number: search.case_number || undefined,
        page: 1,
      });
      const next = (data.cases ?? []).slice(0, 5).map((c: { id: number; case_number: string; title: string }) => ({
        id: c.id,
        case_number: c.case_number,
        title: c.title,
      }));
      setHits(next);
      // What the imperative search_cases tool returns for the same search.
      reportAgent?.(true, caseSearchResult(data));
      pushToast(next.length ? `Found ${data.total}` : 'No matches', next.length ? 'success' : 'error');
    } catch (err) {
      reportAgent?.(false, apiErrorResult(err) ?? toolError('The search failed.', 'unavailable'));
      pushToast(err instanceof Error ? err.message : 'Search failed', 'error');
    } finally {
      setSearching(false);
    }
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // The submitted fields, which an agent may have filled, not state from the last render.
    const fields = new FormData(event.currentTarget);
    const search = {
      party_name: String(fields.get('party_name') ?? '').trim(),
      case_number: String(fields.get('case_number') ?? '').trim(),
    };
    void runSearch(search, trackAgentSubmission(event, 'search_cases_form', { ...search, surface: 'agent_hub' }));
  };

  return (
    <section className="agent-hub-declarative">
      <h2>Case search</h2>
      <form
        className="agent-declarative-form"
        toolname="search_cases_form"
        tooldescription="Search Michigan public court records by party name and case number"
        onSubmit={onSubmit}
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
