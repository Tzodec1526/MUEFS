import { useEffect, useState, type ReactNode } from 'react';
import { Building2, FileStack, FolderSearch, Gavel, Upload } from 'lucide-react';
import { getPublicStats, type PublicPlatformStats } from '../../api/public';

function StatCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="platform-stat-card">
      <div className="platform-stat-icon" aria-hidden="true">{icon}</div>
      <div className="platform-stat-value">{value}</div>
      <div className="platform-stat-label">{label}</div>
      {sub ? <div className="platform-stat-sub">{sub}</div> : null}
    </div>
  );
}

function PlatformStats() {
  const [stats, setStats] = useState<PublicPlatformStats | null>(null);

  useEffect(() => {
    getPublicStats()
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  if (!stats) return null;

  return (
    <section className="platform-stats" aria-labelledby="platform-stats-heading">
      <h2 id="platform-stats-heading" className="platform-stats-title">
        Platform
      </h2>
      <div className="platform-stats-grid">
        <StatCard
          icon={<Building2 size={22} />}
          label="Courts"
          value="All Michigan courts"
        />
        <StatCard
          icon={<FolderSearch size={22} />}
          label="Public cases indexed"
          value={stats.public_cases_indexed}
        />
        <StatCard
          icon={<FileStack size={22} />}
          label="Filings in system"
          value={stats.total_filings}
        />
        <StatCard
          icon={<Gavel size={22} />}
          label="Awaiting clerk review"
          value={stats.pending_clerk_review}
        />
        <StatCard
          icon={<Upload size={22} />}
          label="Max upload"
          value={`${stats.max_upload_mb} MB`}
          sub={`MiFILE caps at ${stats.mifile_max_upload_mb} MB`}
        />
        <StatCard
          icon={<FileStack size={22} />}
          label="MCR document types"
          value={stats.mcr_document_types}
        />
      </div>
    </section>
  );
}

export default PlatformStats;
