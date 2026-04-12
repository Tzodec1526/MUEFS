import { useState, useEffect } from 'react';
import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom';
import { apiClient } from './api/client';
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
import LoginScreen, { getDemoRole, getDemoCourtName } from './components/auth/LoginScreen';

function RequireRole({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  if (!getDemoRole() && location.pathname !== '/login') {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function RequireClerk({ children }: { children: React.ReactNode }) {
  if (getDemoRole() !== 'clerk') {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

function RequireFiler({ children }: { children: React.ReactNode }) {
  const r = getDemoRole();
  if (r === 'clerk' || r === 'public') {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

function FilerDashboard() {
  const [stats, setStats] = useState<{
    total_courts: number;
    counties_covered: number;
    total_case_types: number;
  } | null>(null);

  useEffect(() => {
    apiClient.get('/admin/public-stats').then(res => {
      setStats(res.data);
    }).catch(() => { /* use fallback */ });
  }, []);

  return (
    <div className="dashboard">
      <div className="dashboard-welcome">
        <h2>Michigan Unified E-Filing System</h2>
        <p>File court documents electronically with any Michigan court, 24/7.</p>
      </div>

      <div className="dashboard-stats">
        <div className="stat-card accent">
          <span className="stat-number">{stats?.total_courts ?? '...'}</span>
          <span className="stat-label">Courts</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{stats?.counties_covered ?? '...'}</span>
          <span className="stat-label">Counties</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{stats?.total_case_types ?? '...'}</span>
          <span className="stat-label">Case Types</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">24/7</span>
          <span className="stat-label">Available</span>
        </div>
      </div>

      <div className="dashboard-cards">
        <div className="card card-primary">
          <div className="card-icon">+</div>
          <h3>New Filing</h3>
          <p>File a new document with any Michigan court.</p>
          <Link to="/filing/new" className="btn btn-primary">Start Filing</Link>
        </div>
        <div className="card">
          <div className="card-icon">&#128196;</div>
          <h3>My Filings</h3>
          <p>View and manage your submitted filings.</p>
          <Link to="/filings" className="btn btn-secondary">View Filings</Link>
        </div>
        <div className="card">
          <div className="card-icon">&#128269;</div>
          <h3>Case Search</h3>
          <p>Search cases across all Michigan courts.</p>
          <Link to="/cases/search" className="btn btn-secondary">Search Cases</Link>
        </div>
      </div>
    </div>
  );
}

function PublicDashboard() {
  return (
    <div className="dashboard">
      <div className="dashboard-welcome">
        <h2>Public court records</h2>
        <p>
          Signed-in transparency access: search and open non-sealed matters. Draft filings and
          sealed cases stay restricted to parties, counsel, and court staff.
        </p>
      </div>
      <div className="dashboard-cards">
        <div className="card card-primary">
          <div className="card-icon">&#128269;</div>
          <h3>Case Search</h3>
          <p>Browse the public docket index (sealed cases are excluded from search).</p>
          <Link to="/cases/search" className="btn btn-primary">Search Cases</Link>
        </div>
        <div className="card">
          <div className="card-icon">&#128202;</div>
          <h3>Coverage Stats</h3>
          <p>Statewide court coverage data.</p>
          <Link to="/stats" className="btn btn-secondary">View Stats</Link>
        </div>
      </div>
    </div>
  );
}

function ClerkDashboard() {
  const courtName = getDemoCourtName() || '3rd Circuit Court - Wayne County';
  return (
    <div className="dashboard">
      <div className="dashboard-welcome">
        <h2>{courtName}</h2>
        <p>Clerk Review Dashboard</p>
      </div>

      <div className="dashboard-cards">
        <div className="card card-primary">
          <div className="card-icon">&#128203;</div>
          <h3>Review Queue</h3>
          <p>Review and process pending filings for your court.</p>
          <Link to="/clerk/queue" className="btn btn-primary">Open Queue</Link>
        </div>
        <div className="card">
          <div className="card-icon">&#128269;</div>
          <h3>Case Search</h3>
          <p>Search cases across all Michigan courts.</p>
          <Link to="/cases/search" className="btn btn-secondary">Search Cases</Link>
        </div>
        <div className="card">
          <div className="card-icon">&#128202;</div>
          <h3>Coverage Stats</h3>
          <p>View statewide court coverage data.</p>
          <Link to="/stats" className="btn btn-secondary">View Stats</Link>
        </div>
      </div>
    </div>
  );
}

function Dashboard() {
  const role = getDemoRole();
  if (role === 'clerk') {
    return <ClerkDashboard />;
  }
  if (role === 'public') {
    return <PublicDashboard />;
  }
  return <FilerDashboard />;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginScreen />} />
      {/* Authenticated routes */}
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
                    <Route path="/filing/new" element={<RequireFiler><FilingWizard /></RequireFiler>} />
                    <Route path="/filings" element={<RequireFiler><MyFilings /></RequireFiler>} />
                    <Route path="/cases/search" element={<CaseSearch />} />
                    <Route path="/cases/:caseId" element={<CaseDetailPage />} />
                    <Route path="/favorites" element={<RequireFiler><Favorites /></RequireFiler>} />
                    <Route path="/clerk/queue" element={<RequireClerk><ReviewQueue /></RequireClerk>} />
                    <Route path="/stats" element={<CoverageStats />} />
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
