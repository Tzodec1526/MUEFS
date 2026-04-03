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
      <div className="dashboard-welcome">
        <h2>Michigan Unified E-Filing System</h2>
        <p>File court documents electronically with any Michigan court, 24/7.</p>
      </div>

      {/* Quick Stats */}
      <div className="dashboard-stats">
        <div className="stat-card accent">
          <span className="stat-number">256</span>
          <span className="stat-label">Courts</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">83</span>
          <span className="stat-label">Counties</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">135+</span>
          <span className="stat-label">Filing Types</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">24/7</span>
          <span className="stat-label">Available</span>
        </div>
      </div>

      {/* Action Cards */}
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
