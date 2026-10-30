import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listFilings, type FilingSummary } from '../../api/filings';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import { filingStatusLabel } from '../../utils/filingStatus';
import { formatShortDate } from '../../utils/format';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

const RECENT_FILINGS = 5;

function filingLink(filing: FilingSummary): string {
  return filing.submitted_at && filing.status !== 'returned'
    ? `/filings/${filing.id}/history`
    : `/filing/new?filing_id=${filing.id}`;
}

function FilerDashboard() {
  usePageTitle('Your filings');
  const [overview, setOverview] = useState<Awaited<ReturnType<typeof listFilings>> | null>(null);
  const [error, setError] = useState<LoadFailure | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    listFilings({ page_size: RECENT_FILINGS }).then((result) => {
      if (!current) return;
      setError(null);
      setOverview(result);
    }).catch((err) => {
      if (current) setError(loadFailure(err, 'Could not load your filings.'));
    });
    return () => { current = false; };
  }, [attempt]);

  const draftCount = overview?.status_counts.draft ?? 0;
  const returnedCount = overview?.status_counts.returned ?? 0;

  return (
    <div className="dashboard">
      <div className="page-header">
        <PageHeading>Your filings</PageHeading>
        <Link to="/filing/new" className="btn btn-primary">Start a filing</Link>
      </div>

      {error && <LoadError failure={error} onRetry={() => setAttempt(n => n + 1)} />}
      {!error && !overview && <p className="loading" role="status">Loading your filings...</p>}

      {(draftCount || returnedCount) ? (
        <div className="dashboard-alert-row">
          {returnedCount ? (
            <Link to="/filings?status=returned" className="dashboard-alert dashboard-alert-warn">
              <strong>{returnedCount}</strong> returned for correction
            </Link>
          ) : null}
          {draftCount ? (
            <Link to="/filings?status=draft" className="dashboard-alert">
              <strong>{draftCount}</strong> draft{draftCount === 1 ? '' : 's'} in progress
            </Link>
          ) : null}
        </div>
      ) : null}

      {overview && (
        <section aria-labelledby="recent-filings-heading">
          <h2 id="recent-filings-heading">Recent filings</h2>
          {overview.filings.length === 0 ? (
            <p>You have no filings yet. Start a filing to open your first case or file in an existing one.</p>
          ) : (
            <>
              <ul className="recent-filings">
                {overview.filings.map(filing => (
                  <li key={filing.id}>
                    <Link to={filingLink(filing)}>{filing.case_title || 'Untitled filing'}</Link>
                    <span className={`status-badge ${filing.status}`}>{filingStatusLabel(filing.status)}</span>
                    <span className="recent-filing-meta">
                      {overview.court_names[filing.court_id] || `Court #${filing.court_id}`}
                      {' · '}{formatShortDate(filing.submitted_at || filing.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
              <p><Link to="/filings">All filings</Link></p>
            </>
          )}
        </section>
      )}
    </div>
  );
}

export default FilerDashboard;
