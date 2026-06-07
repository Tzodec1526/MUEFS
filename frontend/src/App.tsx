import { useState, useEffect } from 'react';
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
import LoginScreen, { getDemoRole, getDemoCourtName } from './components/auth/LoginScreen';
import { listFilings, getClerkQueue } from './api/filings';

function RequireRole({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  // Public docket routes are open to anonymous visitors (no account). Everything else
  // requires a (demo) role and bounces unauthenticated visitors to the login screen.
  const isPublicPath = location.pathname.startsWith('/cases');
  if (!getDemoRole() && !isPublicPath && location.pathname !== '/login') {
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
  const [draftCount, setDraftCount] = useState<number | null>(null);
  const [returnedCount, setReturnedCount] = useState<number | null>(null);
  useEffect(() => {
    listFilings({ status: 'draft' }).then((r) => setDraftCount(r.total)).catch(() => {});
    listFilings({ status: 'returned' }).then((r) => setReturnedCount(r.total)).catch(() => {});
  }, []);

  return (
    <div className="dashboard">
      <div className="dashboard-welcome">
        <h2>Your filings</h2>
        <p>File court documents electronically with any Michigan court.</p>
      </div>

      {(draftCount || returnedCount) ? (
        <div className="dashboard-alert-row">
          {draftCount ? (
            <Link to="/filings" className="dashboard-alert">
              <strong>{draftCount}</strong> draft{draftCount === 1 ? '' : 's'} in progress
            </Link>
          ) : null}
          {returnedCount ? (
            <Link to="/filings" className="dashboard-alert dashboard-alert-warn">
              <strong>{returnedCount}</strong> returned for correction
            </Link>
          ) : null}
        </div>
      ) : null}

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
          No account needed: search and open non-sealed matters. Draft filings and sealed cases
          stay restricted to parties, counsel, and court staff.
        </p>
      </div>
      <div className="dashboard-cards">
        <div className="card card-primary">
          <div className="card-icon">&#128269;</div>
          <h3>Case Search</h3>
          <p>Browse the public docket index (sealed cases are excluded from search).</p>
          <Link to="/cases/search" className="btn btn-primary">Search Cases</Link>
        </div>
      </div>
    </div>
  );
}

function ClerkDashboard() {
  const courtName = getDemoCourtName() || '3rd Circuit Court - Wayne County';
  const courtId = parseInt(localStorage.getItem('demo_court_id') || '3', 10);
  const [pending, setPending] = useState<number | null>(null);
  useEffect(() => {
    getClerkQueue(courtId, 1, 'all').then((r) => setPending(r.total)).catch(() => {});
  }, [courtId]);

  return (
    <div className="dashboard">
      <div className="dashboard-welcome">
        <h2>{courtName}</h2>
        <p>
          Clerk Review Dashboard
          {pending !== null ? ` — ${pending} filing${pending === 1 ? '' : 's'} pending review` : ''}
        </p>
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

function NotFound() {
  return (
    <div className="empty-state">
      <h3>Page not found</h3>
      <p>The page you&apos;re looking for doesn&apos;t exist or has moved.</p>
      <Link to="/" className="btn btn-primary">Go to dashboard</Link>
    </div>
  );
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
              <a className="skip-link" href="#main-content">Skip to main content</a>
              <Header />
              <div className="app-body">
                <Sidebar />
                <main className="main-content" id="main-content" tabIndex={-1}>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/filing/new" element={<RequireFiler><FilingWizard /></RequireFiler>} />
                    <Route path="/filings" element={<RequireFiler><MyFilings /></RequireFiler>} />
                    <Route path="/cases/search" element={<CaseSearch />} />
                    <Route path="/cases/:caseId" element={<CaseDetailPage />} />
                    <Route path="/favorites" element={<RequireFiler><Favorites /></RequireFiler>} />
                    <Route path="/clerk/queue" element={<RequireClerk><ReviewQueue /></RequireClerk>} />
                    <Route path="*" element={<NotFound />} />
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
