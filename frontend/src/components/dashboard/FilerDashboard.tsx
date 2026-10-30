import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FilePlus2, FolderOpen, Search } from 'lucide-react';
import { getFilingStatusCounts } from '../../api/filings';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

function FilerDashboard() {
  usePageTitle('Your filings');
  const [draftCount, setDraftCount] = useState<number | null>(null);
  const [returnedCount, setReturnedCount] = useState<number | null>(null);
  const [countsError, setCountsError] = useState<LoadFailure | null>(null);
  const [countsAttempt, setCountsAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    getFilingStatusCounts().then((counts) => {
      if (!current) return;
      setCountsError(null);
      setDraftCount(counts.draft);
      setReturnedCount(counts.returned);
    }).catch((err) => {
      if (current) setCountsError(loadFailure(err, 'Could not load your filing counts.'));
    });
    return () => { current = false; };
  }, [countsAttempt]);

  return (
    <div className="dashboard">
      <div className="dashboard-welcome">
        <PageHeading>Your filings</PageHeading>
        <p>File court documents electronically.</p>
      </div>

      {countsError && <LoadError failure={countsError} onRetry={() => setCountsAttempt(n => n + 1)} />}

      {(draftCount || returnedCount) ? (
        <div className="dashboard-alert-row">
          {draftCount ? (
            <Link to="/filings" className="dashboard-alert">
              <strong>{draftCount}</strong> draft{draftCount === 1 ? '' : 's'} in progress
            </Link>
          ) : null}
          {returnedCount ? (
            <Link to="/filings" className="dashboard-alert dashboard-alert-warn">
              <strong>{returnedCount}</strong> returned for correction
            </Link>
          ) : null}
        </div>
      ) : null}

      <div className="dashboard-cards">
        <div className="card card-primary">
          <div className="card-icon"><FilePlus2 size={22} aria-hidden="true" /></div>
          <h3>New Filing</h3>
          <p>Start a new case or file in an existing one.</p>
          <Link to="/filing/new" className="btn btn-primary">Start Filing</Link>
        </div>
        <div className="card">
          <div className="card-icon"><FolderOpen size={22} aria-hidden="true" /></div>
          <h3>My Filings</h3>
          <p>View and manage your submitted filings.</p>
          <Link to="/filings" className="btn btn-secondary">View Filings</Link>
        </div>
        <div className="card">
          <div className="card-icon"><Search size={22} aria-hidden="true" /></div>
          <h3>Case Search</h3>
          <p>Search court case records.</p>
          <Link to="/cases/search" className="btn btn-secondary">Search Cases</Link>
        </div>
      </div>
    </div>
  );
}

export default FilerDashboard;
