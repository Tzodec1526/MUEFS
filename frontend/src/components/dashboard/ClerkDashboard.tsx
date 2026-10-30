import { useContext, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CourtContext, StaffCourtSelect } from '../auth/CourtSession';
import { getClerkQueue, type ClerkQueue } from '../../api/filings';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

function ClerkDashboard() {
  const { court } = useContext(CourtContext)!;
  const courtId = court!.court_id;
  usePageTitle('Clerk dashboard', court!.court_name || `Court ${courtId}`);
  const [queue, setQueue] = useState<ClerkQueue | null>(null);
  const [queueError, setQueueError] = useState<LoadFailure | null>(null);
  const [queueAttempt, setQueueAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getClerkQueue(courtId, { page_size: 1, signal: controller.signal }).then((result) => {
      if (controller.signal.aborted) return;
      setQueueError(null);
      setQueue(result);
    }).catch((err) => {
      if (!controller.signal.aborted) setQueueError(loadFailure(err, 'Could not load the number of filings pending review.'));
    });
    return () => controller.abort();
  }, [courtId, queueAttempt]);

  return (
    <div className="dashboard">
      <StaffCourtSelect />
      <div className="page-header">
        <div>
          <PageHeading>{court!.court_name || `Court ${courtId}`}</PageHeading>
          <p className="dashboard-summary">
            {queue ? `${queue.total} filing${queue.total === 1 ? '' : 's'} pending review` : 'Clerk dashboard'}
          </p>
        </div>
        <Link to="/clerk/queue" className="btn btn-primary">Open review queue</Link>
      </div>
      {queueError && <LoadError failure={queueError} onRetry={() => setQueueAttempt(n => n + 1)} />}
      {queue && (
        <dl className="queue-counts">
          <div><dt>Submitted</dt><dd>{queue.submitted_count}</dd></div>
          <div><dt>Under review</dt><dd>{queue.under_review_count}</dd></div>
          <div><dt>Waiting 48+ hours</dt><dd>{queue.waiting_48h}</dd></div>
        </dl>
      )}
    </div>
  );
}

export default ClerkDashboard;
