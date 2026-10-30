import { useEffect, useRef, useState } from 'react';
import { searchCases } from '../../api/cases';
import { getCaseTypes } from '../../api/courts';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import { actionErrorMessage } from '../../api/client';
import { emitToast } from '../../utils/toastBus';

export interface CaseResult {
  id: number;
  case_number: string;
  title: string;
  case_type_id: number;
  status: string;
}

interface Props {
  courtId: number;
  courtName: string;
  selectedCaseId: number | null;
  isNewChosen: boolean;
  onChooseExisting: () => void;
  onSelectExisting: (c: CaseResult, caseTypeName: string) => void;
  onSelectNew: () => void;
}

function CaseSelector({
  courtId, courtName, selectedCaseId, isNewChosen, onChooseExisting, onSelectExisting, onSelectNew,
}: Props) {
  const [mode, setMode] = useState<'existing' | 'new' | null>(
    selectedCaseId ? 'existing' : isNewChosen ? 'new' : null
  );
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CaseResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [typeNames, setTypeNames] = useState<Record<string, string>>({});
  const [error, setError] = useState<LoadFailure | null>(null);
  const searchRequest = useRef<AbortController>();

  useEffect(() => () => searchRequest.current?.abort(), [courtId]);

  // Resolve case-type names so an existing-case selection carries a readable
  // type through to the review screen (existing cases skip the case-type step).
  // Existing cases keep types the court has since closed to new cases, so include those.
  useEffect(() => {
    let active = true;
    getCaseTypes(courtId, true)
      .then((types) => {
        if (active) setTypeNames(Object.fromEntries(types.map((t) => [t.id, t.name] as const)));
      })
      .catch((err: unknown) => {
        const message = active && actionErrorMessage(err, 'Could not load the case type names.');
        if (message) emitToast(message, 'error');
      });
    return () => {
      active = false;
    };
  }, [courtId]);

  const runSearch = async () => {
    if (!query.trim()) return;
    searchRequest.current?.abort();
    const controller = new AbortController();
    searchRequest.current = controller;
    setSearching(true);
    setHasSearched(true);
    setError(null);
    try {
      // Search by case number AND by party name, then merge — one box, either input.
      const [byNum, byParty] = await Promise.all([
        searchCases({ court_id: courtId, case_number: query.trim() }, controller.signal),
        searchCases({ court_id: courtId, party_name: query.trim() }, controller.signal),
      ]);
      if (controller.signal.aborted) return;
      const byId = new Map<number, CaseResult>();
      [...(byNum.cases || []), ...(byParty.cases || [])].forEach((c: CaseResult) => byId.set(c.id, c));
      setResults([...byId.values()]);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(loadFailure(err, 'Case search is unavailable right now. Please try again.'));
      setResults([]);
    } finally {
      if (!controller.signal.aborted) setSearching(false);
    }
  };

  return (
    <div className="form-section">
      <h3>Existing case or new case?</h3>
      <p className="info-text">
        Most filings go into a case that already exists. Search for it below, or start a new case.
      </p>

      <div className="case-choice-cards">
        <button
          type="button"
          className={`case-choice-card ${mode === 'existing' ? 'selected' : ''}`}
          onClick={() => { setMode('existing'); onChooseExisting(); }}
          aria-pressed={mode === 'existing'}
        >
          <div className="case-choice-icon">&#128269;</div>
          <h4>File into an existing case</h4>
          <p>Search by case number or party name in {courtName || 'this court'}.</p>
        </button>
        <button
          type="button"
          className={`case-choice-card ${mode === 'new' ? 'selected' : ''}`}
          onClick={() => { setMode('new'); if (!isNewChosen) onSelectNew(); }}
          aria-pressed={mode === 'new'}
        >
          <div className="case-choice-icon">+</div>
          <h4>Start a new case</h4>
          <p>Initiate a new matter, e.g. a complaint or petition.</p>
        </button>
      </div>

      {mode === 'existing' && (
        <div className="case-search-inline">
          <div className="form-row">
            <div className="form-group form-group-grow">
              <label htmlFor="caseQuery">Case number or party name</label>
              <input
                id="caseQuery"
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') runSearch(); }}
                placeholder="e.g., 2026-000001-CZ or Smith"
              />
            </div>
            <button className="btn btn-primary" onClick={runSearch} disabled={searching || !query.trim()}>
              {searching ? 'Searching...' : 'Search'}
            </button>
          </div>

          {error && <LoadError failure={error} onRetry={runSearch} />}
          {!error && hasSearched && !searching && (
            results.length > 0 ? (
              <table className="review-table case-results">
                <thead>
                  <tr><th></th><th>Case Number</th><th>Title</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {results.map((c) => (
                    <tr key={c.id} className={selectedCaseId === c.id ? 'selected-row' : ''}>
                      <td>
                        <button
                          className={`btn btn-small ${selectedCaseId === c.id ? 'btn-primary' : 'btn-secondary'}`}
                          onClick={() => onSelectExisting(c, typeNames[c.case_type_id] || '')}
                        >
                          {selectedCaseId === c.id ? 'Selected' : 'Select'}
                        </button>
                      </td>
                      <td>{c.case_number}</td>
                      <td>{c.title}</td>
                      <td><span className={`status-badge ${c.status}`}>{c.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="info-text">No matching cases found. Check the number/name, or start a new case.</p>
            )
          )}
        </div>
      )}

      {mode === 'new' && (
        <div className="alert alert-info">
          Starting a <strong>new case</strong> in {courtName || 'the selected court'}. Next, choose the case type.
        </div>
      )}
    </div>
  );
}

export default CaseSelector;
