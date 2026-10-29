import { lazy, Suspense, useState, useEffect, useContext } from 'react';
import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom';
import { FilePlus2, FolderOpen, Search, ClipboardCheck } from 'lucide-react';
import Header from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import Footer from './components/layout/Footer';
import LoginScreen, { hasAdministrationAccess, hasSession } from './components/auth/LoginScreen';
import { CourtContext, CourtSession, CourtWorkspace, StaffCourtSelect } from './components/auth/CourtSession';
import PlatformStats from './components/marketing/PlatformStats';
import MifileComparison from './components/marketing/MifileComparison';
import { getFilingStatusCounts, getClerkQueue } from './api/filings';
import { oidcSessionExpected, SESSION_KEY } from './auth/keycloak';
import LoadError from './components/common/LoadError';
import { loadFailure, type LoadFailure } from './utils/errors';

const FilingWizard = lazy(() => import('./components/filing/FilingWizard'));
const MyFilings = lazy(() => import('./components/filing/MyFilings'));
const FilingHistoryPage = lazy(() => import('./components/filing/FilingHistoryPage'));
const FilingDateOrderPage = lazy(() => import('./components/clerk/FilingDateOrderPage'));
const FilingFeesPage = lazy(() => import('./components/filing/FilingFeesPage'));
const FeeReviewQueue = lazy(() => import('./components/clerk/FeeReviewQueue'));
const PaymentRegisterPage = lazy(() => import('./components/clerk/PaymentRegisterPage'));
const ReviewQueue = lazy(() => import('./components/clerk/ReviewQueue'));
const CourtCaseDirectory = lazy(() => import('./components/courts/CourtCaseDirectory'));
const DocumentPublicationPage = lazy(() => import('./components/courts/DocumentPublicationPage'));
const CaseParticipantsPage = lazy(() => import('./components/courts/CaseParticipantsPage'));
const ServiceContactPage = lazy(() => import('./components/courts/ServiceContactPage'));
const DeliveriesPage = lazy(() => import('./components/service/DeliveriesPage'));
const DeliveryComposePage = lazy(() => import('./components/service/DeliveryComposePage'));
const DeliveryDetailPage = lazy(() => import('./components/service/DeliveryDetailPage'));
const CourtCalendarPage = lazy(() => import('./components/courts/CourtCalendarPage'));
const CourtIntakePage = lazy(() => import('./components/courts/CourtIntakePage'));
const NotificationsPage = lazy(() => import('./components/notifications/NotificationsPage'));
const AdministrationPage = lazy(() => import('./components/admin/AdministrationPage'));
const CaseSearch = lazy(() => import('./components/search/CaseSearch'));
const Favorites = lazy(() => import('./components/search/Favorites'));
const CaseDetailPage = lazy(() => import('./components/search/CaseDetailPage'));
const AuthCallback = lazy(() => import('./components/auth/AuthCallback'));

function RequireRole({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  // Preserve private portal destinations while the visitor signs in.
  const isPublicPath =
    /^\/cases\/(search|\d+)\/?$/.test(location.pathname)
    || location.pathname.startsWith('/courts/');
  if (!hasSession() && !isPublicPath && location.pathname !== '/login') {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search + location.hash)}`} replace />;
  }
  return <>{children}</>;
}

function RequireFiler({ children }: { children: React.ReactNode }) {
  const { role: r } = useContext(CourtContext)!;
  if (r === 'clerk' || r === 'admin' || r === 'public') {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

function RequireAdministration({ children }: { children: React.ReactNode }) {
  const { loading } = useContext(CourtContext)!;
  if (loading) return <p className="loading" role="status">Checking administrator access…</p>;
  if (!hasAdministrationAccess()) {
    return (
      <div className="empty-state">
        <h3>Administrator access required</h3>
        <p>People and court access is managed by system and court administrators.</p>
        <Link to="/" className="btn btn-primary">Go to dashboard</Link>
      </div>
    );
  }
  return <>{children}</>;
}

function FilerDashboard() {
  const [draftCount, setDraftCount] = useState<number | null>(null);
  const [returnedCount, setReturnedCount] = useState<number | null>(null);
  const [countsError, setCountsError] = useState<LoadFailure | null>(null);
  const [countsAttempt, setCountsAttempt] = useState(0);
  useEffect(() => {
    getFilingStatusCounts().then((counts) => {
      setCountsError(null);
      setDraftCount(counts.draft);
      setReturnedCount(counts.returned);
    }).catch((err) => setCountsError(loadFailure(err, 'Could not load your filing counts.')));
  }, [countsAttempt]);

  return (
    <div className="dashboard">
      <div className="dashboard-welcome">
        <h2>Your filings</h2>
        <p>File court documents electronically with any Michigan court.</p>
      </div>

      {countsError && <LoadError failure={countsError} onRetry={() => setCountsAttempt(n => n + 1)} />}

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
          <div className="card-icon"><FilePlus2 size={22} aria-hidden="true" /></div>
          <h3>New Filing</h3>
          <p>File a new document with any Michigan court.</p>
          <Link to="/filing/new" className="btn btn-primary">Start Filing</Link>
        </div>
        <div className="card">
          <div className="card-icon"><FolderOpen size={22} aria-hidden="true" /></div>
          <h3>My Filings</h3>
          <p>View and manage your submitted filings.</p>
          <Link to="/filings" className="btn btn-secondary">View Filings</Link>
        </div>
        <div className="card">
          <div className="card-icon"><Search size={22} aria-hidden="true" /></div>
          <h3>Case Search</h3>
          <p>Search cases across all Michigan courts.</p>
          <Link to="/cases/search" className="btn btn-secondary">Search Cases</Link>
        </div>
      </div>
      <PlatformStats />
      <MifileComparison variant="dashboard" />
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
          <div className="card-icon"><Search size={22} aria-hidden="true" /></div>
          <h3>Case Search</h3>
          <p>Browse the public docket index (sealed cases are excluded from search).</p>
          <Link to="/cases/search" className="btn btn-primary">Search Cases</Link>
        </div>
      </div>
      <PlatformStats />
      <MifileComparison variant="dashboard" />
    </div>
  );
}

function ClerkDashboard() {
  const { court } = useContext(CourtContext)!;
  const courtId = court!.court_id;
  const [pending, setPending] = useState<number | null>(null);
  const [pendingError, setPendingError] = useState<LoadFailure | null>(null);
  const [pendingAttempt, setPendingAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getClerkQueue(courtId, { page_size: 1, signal: controller.signal }).then((r) => {
      if (controller.signal.aborted) return;
      setPendingError(null);
      setPending(r.total);
    }).catch((err) => {
      if (!controller.signal.aborted) setPendingError(loadFailure(err, 'Could not load the number of filings pending review.'));
    });
    return () => controller.abort();
  }, [courtId, pendingAttempt]);

  return (
    <div className="dashboard">
      <StaffCourtSelect />
      <div className="dashboard-welcome">
        <h2>{court!.court_name || `Court ${courtId}`}</h2>
        <p>
          Clerk Review Dashboard
          {pending !== null ? ` — ${pending} filing${pending === 1 ? '' : 's'} pending review` : ''}
        </p>
      </div>
      {pendingError && <LoadError failure={pendingError} onRetry={() => setPendingAttempt(n => n + 1)} />}

      <div className="dashboard-cards">
        <div className="card card-primary">
          <div className="card-icon"><ClipboardCheck size={22} aria-hidden="true" /></div>
          <h3>Review Queue</h3>
          <p>Review and process pending filings for your court.</p>
          <Link to="/clerk/queue" className="btn btn-primary">Open Queue</Link>
        </div>
        <div className="card">
          <div className="card-icon"><Search size={22} aria-hidden="true" /></div>
          <h3>Case Search</h3>
          <p>Search cases across all Michigan courts.</p>
          <Link to="/cases/search" className="btn btn-secondary">Search Cases</Link>
        </div>
      </div>
      <PlatformStats />
    </div>
  );
}

function Dashboard() {
  const { role } = useContext(CourtContext)!;
  if (role === 'admin') return <Navigate to="/admin" replace />;
  if (role === 'clerk') {
    return <CourtWorkspace><ClerkDashboard /></CourtWorkspace>;
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
  const location = useLocation();
  const [sessionEpoch, setSessionEpoch] = useState(0);
  useEffect(() => {
    const sessionChanged = (event: StorageEvent) => {
      if (event.storageArea !== localStorage) return;
      if (event.key === null || (event.oldValue !== event.newValue && (
        event.key === SESSION_KEY || (event.key === 'demo_role' && !oidcSessionExpected())
      ))) setSessionEpoch(value => value + 1);
    };
    window.addEventListener('storage', sessionChanged);
    return () => window.removeEventListener('storage', sessionChanged);
  }, []);
  return (
    <Suspense fallback={<p className="loading" role="status">Loading page...</p>}>
      <Routes>
        <Route path="/login" element={<LoginScreen />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        {/* Authenticated routes */}
        <Route
          path="*"
          element={
            <RequireRole>
              <CourtSession key={sessionEpoch}>
              <div className="app-layout">
                <a className="skip-link" href="#main-content">Skip to main content</a>
                <Header />
                <div className="app-body">
                  <Sidebar />
                  <main className="main-content" id="main-content" tabIndex={-1}>
                    <Suspense fallback={<p className="loading" role="status">Loading page...</p>}>
                      <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/filing/new" element={<RequireFiler><FilingWizard key={location.key} /></RequireFiler>} />
                        <Route path="/filings" element={<RequireFiler><MyFilings /></RequireFiler>} />
                        <Route path="/filings/:filingId/history" element={<FilingHistoryPage key={location.pathname} />} />
                        <Route path="/filings/:filingId/fees" element={<FilingFeesPage key={location.pathname} />} />
                        <Route path="/filings/:filingId/filing-date" element={<CourtWorkspace><FilingDateOrderPage key={location.pathname} /></CourtWorkspace>} />
                        <Route path="/cases/search" element={<CaseSearch />} />
                        <Route path="/courts/:courtId/calendar" element={<CourtCalendarPage key={location.pathname} />} />
                        <Route path="/courts/:courtId/intake" element={<CourtIntakePage key={location.pathname} />} />
                        <Route path="/notifications" element={<NotificationsPage />} />
                        <Route path="/service/deliveries" element={<DeliveriesPage key={location.pathname} />} />
                        <Route path="/service/deliveries/:deliveryId" element={<DeliveryDetailPage key={location.pathname} />} />
                        <Route path="/filings/:filingId/deliveries" element={<DeliveriesPage key={location.pathname} />} />
                        <Route path="/filings/:filingId/deliveries/new" element={<DeliveryComposePage key={location.pathname} />} />
                        <Route path="/admin" element={<RequireAdministration><AdministrationPage /></RequireAdministration>} />
                        <Route path="/cases/:caseId/participants" element={<CourtWorkspace><CaseParticipantsPage /></CourtWorkspace>} />
                        <Route path="/cases/:caseId/participants/:participantId/service-contact" element={<CourtWorkspace><ServiceContactPage /></CourtWorkspace>} />
                        <Route path="/clerk/cases" element={<CourtWorkspace><CourtCaseDirectory /></CourtWorkspace>} />
                        <Route path="/documents/:documentId/publication" element={<CourtWorkspace><DocumentPublicationPage /></CourtWorkspace>} />
                        <Route path="/cases/:caseId" element={<CaseDetailPage />} />
                        <Route path="/favorites" element={<RequireFiler><Favorites /></RequireFiler>} />
                        <Route path="/clerk/queue" element={<CourtWorkspace><ReviewQueue /></CourtWorkspace>} />
                        <Route path="/clerk/fee-reviews" element={<CourtWorkspace><FeeReviewQueue /></CourtWorkspace>} />
                        <Route path="/clerk/payment-register" element={<CourtWorkspace><PaymentRegisterPage /></CourtWorkspace>} />
                        <Route path="*" element={<NotFound />} />
                      </Routes>
                    </Suspense>
                  </main>
                </div>
                <Footer />
              </div>
              </CourtSession>
            </RequireRole>
          }
        />
      </Routes>
    </Suspense>
  );
}

export default App;
