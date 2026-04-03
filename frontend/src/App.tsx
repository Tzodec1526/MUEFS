import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom';
import Header from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import Footer from './components/layout/Footer';
import FilingWizard from './components/filing/FilingWizard';
import MyFilings from './components/filing/MyFilings';
import ReviewQueue from './components/clerk/ReviewQueue';
import CaseSearch from './components/search/CaseSearch';
import Favorites from './components/search/Favorites';
import CaseDetailPage from './components/search/CaseDetailPage';
import CoverageStats from './components/stats/CoverageStats';
import LoginScreen, { getDemoRole } from './components/auth/LoginScreen';

function RequireRole({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  if (!getDemoRole() && location.pathname !== '/login') {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function Dashboard() {
  return (
    <div className="dashboard">
      {/* Hero Section */}
      <div className="hero-section">
        <h2>One System. Every Court. Every Michigander.</h2>
        <p>
          File with any of Michigan's 256 courts from anywhere, anytime.
          No more juggling multiple systems, incompatible formats, or driving to the courthouse.
        </p>
      </div>

      {/* Problem Statement */}
      <div className="section-heading">
        <h3>The Problem</h3>
      </div>
      <div className="problem-cards">
        <div className="problem-card">
          <div className="problem-card-icon">{'\uD83D\uDD17'}</div>
          <h4>Fragmented System</h4>
          <p>
            Michigan's current e-filing requires different systems for different courts.
            Attorneys waste hours navigating incompatible platforms.
          </p>
        </div>
        <div className="problem-card">
          <div className="problem-card-icon">{'\uD83D\uDEA7'}</div>
          <h4>Access Barriers</h4>
          <p>
            Self-represented litigants face complex procedures with no guidance.
            Fee waiver processes vary by court. Rural residents must drive hours to file.
          </p>
        </div>
        <div className="problem-card">
          <div className="problem-card-icon">{'\uD83D\uDCCB'}</div>
          <h4>Administrative Burden</h4>
          <p>
            Court clerks re-enter data between systems. No unified case search.
            Filing errors cause delays and additional costs.
          </p>
        </div>
      </div>

      {/* Solution Cards */}
      <div className="section-heading">
        <h3>The MUEFS Solution</h3>
      </div>
      <div className="solution-cards">
        <div className="solution-card">
          <div className="solution-card-stat">256 courts</div>
          <h4>Unified Platform</h4>
          <p>
            One login, 256 courts. Circuit, district, probate, appellate &mdash; all in one system.
          </p>
        </div>
        <div className="solution-card">
          <div className="solution-card-stat">135+ filing types</div>
          <h4>Guided Filing</h4>
          <p>
            Step-by-step wizard with MCR compliance checks.
            Plain-language mode for self-represented litigants.
          </p>
        </div>
        <div className="solution-card">
          <div className="solution-card-stat">$0 licensing</div>
          <h4>Open Source</h4>
          <p>
            Transparent, auditable, community-driven. No vendor lock-in.
            Built on modern, proven technology.
          </p>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="section-heading">
        <h3>Quick Actions</h3>
      </div>
      <div className="dashboard-cards">
        <div className="card card-primary">
          <div className="card-icon">+</div>
          <h3>New Filing</h3>
          <p>File a new document with any Michigan court. Our guided wizard walks you through each step.</p>
          <Link to="/filing/new" className="btn btn-primary">Start Filing</Link>
        </div>
        <div className="card">
          <div className="card-icon">{'\uD83D\uDCC4'}</div>
          <h3>My Filings</h3>
          <p>View, track, and manage all your submitted filings. See real-time status updates.</p>
          <Link to="/filings" className="btn btn-secondary">View Filings</Link>
        </div>
        <div className="card">
          <div className="card-icon">{'\uD83D\uDD0D'}</div>
          <h3>Case Search</h3>
          <p>Search for cases across all Michigan courts by case number or party name.</p>
          <Link to="/cases/search" className="btn btn-secondary">Search Cases</Link>
        </div>
      </div>

      {/* Coverage Footer */}
      <div className="coverage-footer">
        Covering all 83 Michigan counties &mdash; from Wayne to Keweenaw
      </div>
    </div>
  );
}

function StatsPlaceholder() {
  return (
    <div className="dashboard">
      <h2>System Statistics</h2>
      <p>Statistics dashboard coming soon.</p>
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginScreen />} />
      <Route
        path="*"
        element={
          <RequireRole>
            <div className="app-layout">
              <Header />
              <div className="app-body">
                <Sidebar />
                <main className="main-content">
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/filing/new" element={<FilingWizard />} />
                    <Route path="/filings" element={<MyFilings />} />
                    <Route path="/cases/search" element={<CaseSearch />} />
                    <Route path="/cases/:caseId" element={<CaseDetailPage />} />
                    <Route path="/favorites" element={<Favorites />} />
                    <Route path="/clerk/queue" element={<ReviewQueue />} />
                    <Route path="/stats" element={<CoverageStats />} />
                    <Route path="/stats" element={<StatsPlaceholder />} />
                  </Routes>
                </main>
              </div>
              <Footer />
            </div>
          </RequireRole>
        }
      />
    </Routes>
  );
}

export default App;
