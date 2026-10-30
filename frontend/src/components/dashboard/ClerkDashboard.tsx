import { useContext, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ClipboardCheck, Search } from 'lucide-react';
import { CourtContext, StaffCourtSelect } from '../auth/CourtSession';
import PlatformStats from '../marketing/PlatformStats';
import { getClerkQueue } from '../../api/filings';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

function ClerkDashboard() {
  const { court } = useContext(CourtContext)!;
  const courtId = court!.court_id;
  usePageTitle('Clerk dashboard', court!.court_name || `Court ${courtId}`);
  const [pending, setPending] = useState<number | null>(null);
  const [pendingError, setPendingError] = useState<LoadFailure | null>(null);
  const [pendingAttempt, setPendingAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getClerkQueue(courtId, { page_size: 1, signal: controller.signal }).then((r) => {
      if (controller.signal.aborted) return;
      setPendingError(null);
      setPending(r.total);
    }).catch((err) => {
      if (!controller.signal.aborted) setPendingError(loadFailure(err, 'Could not load the number of filings pending review.'));
    });
    return () => controller.abort();
  }, [courtId, pendingAttempt]);

  return (
    <div className="dashboard">
      <StaffCourtSelect />
      <div className="dashboard-welcome">
        <PageHeading>{court!.court_name || `Court ${courtId}`}</PageHeading>
        <p>
          Clerk Review Dashboard
          {pending !== null ? ` — ${pending} filing${pending === 1 ? '' : 's'} pending review` : ''}
        </p>
      </div>
      {pendingError && <LoadError failure={pendingError} onRetry={() => setPendingAttempt(n => n + 1)} />}

      <div className="dashboard-cards">
        <div className="card card-primary">
          <div className="card-icon"><ClipboardCheck size={22} aria-hidden="true" /></div>
          <h3>Review Queue</h3>
          <p>Review and process pending filings for your court.</p>
          <Link to="/clerk/queue" className="btn btn-primary">Open Queue</Link>
        </div>
        <div className="card">
          <div className="card-icon"><Search size={22} aria-hidden="true" /></div>
          <h3>Case Search</h3>
          <p>Search court case records.</p>
          <Link to="/cases/search" className="btn btn-secondary">Search Cases</Link>
        </div>
      </div>
      <PlatformStats />
    </div>
  );
}

export default ClerkDashboard;
