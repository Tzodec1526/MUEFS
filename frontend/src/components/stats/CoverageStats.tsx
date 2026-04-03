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

      {/* Why unified matters */}
      <div className="stats-section">
        <h3>Why Unified Filing Matters</h3>
        <div className="impact-grid">
          <div className="impact-card">
            <div className="impact-icon">$</div>
            <h4>Cost Savings</h4>
            <p>
              One system eliminates redundant licensing fees, training costs, and vendor contracts
              across {stats.total_courts} courts. Estimated savings: <strong>$5-10M annually</strong> in
              reduced IT overhead alone.
            </p>
          </div>
          <div className="impact-card">
            <div className="impact-icon">&#9201;</div>
            <h4>Time Savings</h4>
            <p>
              Attorneys currently spend an average of <strong>15-30 minutes per filing</strong> navigating
              different systems. Unified filing reduces this to under 5 minutes.
            </p>
          </div>
          <div className="impact-card">
            <div className="impact-icon">&#9878;</div>
            <h4>Access to Justice</h4>
            <p>
              Self-represented litigants make up <strong>over 50%</strong> of family law cases.
              Guided filing with plain language and fee waiver support (MCR 2.002) removes barriers.
            </p>
          </div>
          <div className="impact-card">
            <div className="impact-icon">&#128202;</div>
            <h4>Data-Driven Courts</h4>
            <p>
              Unified data enables statewide analytics: filing volumes, processing times,
              and resource allocation. Currently impossible across {Object.keys(stats.courts_by_type).length} different
              court types.
            </p>
          </div>
        </div>
      </div>

      {/* Current problem */}
      <div className="stats-section">
        <h3>The Current Problem</h3>
        <div className="problem-comparison">
          <div className="comparison-col comparison-current">
            <h4>Today (Fragmented)</h4>
            <ul>
              <li>Multiple e-filing vendors with different interfaces</li>
              <li>No unified case search across courts</li>
              <li>Attorneys must learn different systems per court</li>
              <li>Self-represented litigants left behind</li>
              <li>No statewide filing data or analytics</li>
              <li>Vendor lock-in with proprietary systems</li>
            </ul>
          </div>
          <div className="comparison-col comparison-unified">
            <h4>MUEFS (Unified)</h4>
            <ul>
              <li>One login for all {stats.total_courts} courts</li>
              <li>Statewide case search by name, number, or court</li>
              <li>Consistent interface with MCR compliance built in</li>
              <li>Guided filing with plain-language mode</li>
              <li>Real-time analytics and reporting</li>
              <li>Open source — no vendor lock-in</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CoverageStats;
