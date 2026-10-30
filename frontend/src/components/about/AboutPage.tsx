import { useEffect, useState } from 'react';
import { getPublicStats } from '../../api/public';
import { loadFailure } from '../../utils/errors';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';
import MifileComparison from './MifileComparison';
import PlatformStats, { type PublicStatsResult } from './PlatformStats';

function AboutPage() {
  usePageTitle('About');
  const [result, setResult] = useState<PublicStatsResult>();
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    getPublicStats()
      .then(stats => { if (current) setResult({ stats }); })
      .catch(err => { if (current) setResult({ error: loadFailure(err, 'Platform statistics are unavailable right now.') }); });
    return () => { current = false; };
  }, [attempt]);

  return (
    <div className="about-page">
      <PageHeading>About MUEFS</PageHeading>
      <p>
        MUEFS is an open-source demo of one e-filing portal for Michigan courts. It covers filing,
        clerk review, public case search and document delivery. It is not affiliated with SCAO or
        the Michigan Supreme Court, and it is not for real filings.
      </p>
      <MifileComparison stats={result?.stats} />
      <PlatformStats result={result} onRetry={() => setAttempt(n => n + 1)} />
    </div>
  );
}

export default AboutPage;
