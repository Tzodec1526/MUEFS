import { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';

interface StatsData {
  courts_by_type: Record<string, number>;
  total_courts: number;
  counties_covered: number;
  total_case_types: number;
  total_filings: number;
  accepted_filings: number;
}

const COURT_TYPE_LABELS: Record<string, string> = {
  circuit: 'Circuit Courts',
  district: 'District Courts',
  probate: 'Probate Courts',
  court_of_claims: 'Court of Claims',
  court_of_appeals: 'Court of Appeals',
  supreme_court: 'Supreme Court',
};

function CoverageStats() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        const { data } = await apiClient.get('/admin/public-stats');
        setStats(data);
      } catch {
        setStats(null);
      } finally {
        setLoading(false);
      }
    }
    fetchStats();
  }, []);

  if (loading) {
    return (
      <div className="stats-page">
        <h2>Statewide Coverage</h2>
        <p>Loading statistics...</p>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="stats-page">
        <h2>Statewide Coverage</h2>
        <p>Unable to load statistics.</p>
      </div>
    );
  }

  return (
    <div className="stats-page">
      <div className="stats-hero">
        <h2>Statewide Court Coverage</h2>
        <p>MUEFS provides unified e-filing access to every court in Michigan</p>
      </div>

      {/* Top-level stats */}
      <div className="stats-overview">
        <div className="stat-card accent">
          <span className="stat-number">{stats.total_courts}</span>
          <span className="stat-label">Courts Connected</span>
        </div>
        <div className="stat-card accent">
          <span className="stat-number">{stats.counties_covered}</span>
          <span className="stat-label">Counties Covered</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{stats.total_case_types.toLocaleString()}</span>
          <span className="stat-label">Case Types Supported</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{stats.total_filings}</span>
          <span className="stat-label">Filings Processed</span>
        </div>
      </div>

      {/* Courts by type */}
      <div className="stats-section">
        <h3>Courts by Type</h3>
        <div className="court-type-grid">
          {Object.entries(stats.courts_by_type)
            .filter(([, count]) => count > 0)
            .sort(([, a], [, b]) => b - a)
            .map(([type, count]) => (
              <div key={type} className="court-type-card">
                <div className="court-type-count">{count}</div>
                <div className="court-type-label">{COURT_TYPE_LABELS[type] || type}</div>
              </div>
            ))}
        </div>
      </div>

    </div>
  );
}

export default CoverageStats;
