import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

function PublicDashboard() {
  usePageTitle('Public court records');
  const navigate = useNavigate();
  const [caseNumber, setCaseNumber] = useState('');
  const [partyName, setPartyName] = useState('');

  const search = (event: FormEvent) => {
    event.preventDefault();
    const params = new URLSearchParams();
    if (caseNumber.trim()) params.set('case', caseNumber.trim());
    if (partyName.trim()) params.set('party', partyName.trim());
    navigate(`/cases/search?${params}`);
  };

  return (
    <div className="dashboard">
      <PageHeading>Public court records</PageHeading>
      <p className="dashboard-summary">
        No account needed: search and open non-sealed matters. Draft filings and sealed cases
        stay restricted to parties, counsel, and court staff.
      </p>
      <form className="search-form" onSubmit={search}>
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="homeCaseNumber">Case number</label>
            <input id="homeCaseNumber" type="text" value={caseNumber} onChange={(e) => setCaseNumber(e.target.value)} />
          </div>
          <div className="form-group">
            <label htmlFor="homePartyName">Party name</label>
            <input id="homePartyName" type="text" value={partyName} onChange={(e) => setPartyName(e.target.value)} />
          </div>
          <button className="btn btn-primary" type="submit">Search cases</button>
        </div>
      </form>
      <p><Link to="/cases/search">Browse recent public filings</Link></p>
    </div>
  );
}

export default PublicDashboard;
