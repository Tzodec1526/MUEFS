import { useEffect, useState } from 'react';
import { getPublicStats, type PublicPlatformStats } from '../../api/public';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import LoadError from '../common/LoadError';

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="platform-stat-card">
      <div className="platform-stat-value">{value}</div>
      <div className="platform-stat-label">{label}</div>
      {sub ? <div className="platform-stat-label">{sub}</div> : null}
    </div>
  );
}

function PlatformStats() {
  const [result, setResult] = useState<{ stats?: PublicPlatformStats; error?: LoadFailure }>();
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    getPublicStats()
      .then(stats => { if (current) setResult({ stats }); })
      .catch(err => { if (current) setResult({ error: loadFailure(err, 'Platform statistics are unavailable right now.') }); });
    return () => { current = false; };
  }, [attempt]);

  if (!result) return null;
  const heading = <h2 id="platform-stats-heading">Platform statistics</h2>;
  if (!result.stats) {
    return (
      <section className="platform-stats" aria-labelledby="platform-stats-heading">
        {heading}
        <LoadError failure={result.error!} onRetry={() => setAttempt(n => n + 1)} />
      </section>
    );
  }
  const { stats } = result;

  return (
    <section className="platform-stats" aria-labelledby="platform-stats-heading">
      {heading}
      <div className="platform-stats-grid">
        <StatCard label="Courts accepting e-filing" value={stats.courts_efiling_enabled} />
        <StatCard label="Public cases indexed" value={stats.public_cases_indexed} />
        <StatCard label="Filings in system" value={stats.total_filings} />
        <StatCard label="Awaiting clerk review" value={stats.pending_clerk_review} />
        <StatCard
          label="Max upload"
          value={`${stats.max_upload_mb} MB`}
          sub={`MiFILE caps at ${stats.mifile_max_upload_mb} MB`}
        />
        <StatCard label="MCR document types" value={stats.mcr_document_types} />
      </div>
    </section>
  );
}

export default PlatformStats;
