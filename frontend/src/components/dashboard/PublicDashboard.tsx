import { Link } from 'react-router-dom';
import { Search } from 'lucide-react';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

function PublicDashboard() {
  usePageTitle('Public court records');
  return (
    <div className="dashboard">
      <div className="dashboard-welcome">
        <PageHeading>Public court records</PageHeading>
        <p>
          No account needed: search and open non-sealed matters. Draft filings and sealed cases
          stay restricted to parties, counsel, and court staff.
        </p>
      </div>
      <div className="dashboard-cards">
        <div className="card card-primary">
          <div className="card-icon"><Search size={22} aria-hidden="true" /></div>
          <h3>Case Search</h3>
          <p>Browse the public docket index (sealed cases are excluded from search).</p>
          <Link to="/cases/search" className="btn btn-primary">Search Cases</Link>
        </div>
      </div>
    </div>
  );
}

export default PublicDashboard;
