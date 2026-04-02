import { Routes, Route, Link } from 'react-router-dom';
import Header from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import Footer from './components/layout/Footer';
import FilingWizard from './components/filing/FilingWizard';
import MyFilings from './components/filing/MyFilings';
import ReviewQueue from './components/clerk/ReviewQueue';
import CaseSearch from './components/search/CaseSearch';
import Favorites from './components/search/Favorites';

function Dashboard() {
  return (
    <div className="dashboard">
      <div className="dashboard-welcome">
        <h2>Welcome to Michigan Unified E-Filing System</h2>
        <p>File court documents electronically with any Michigan court, 24/7.</p>
      </div>

      {/* Quick Stats */}
      <div className="dashboard-stats">
        <div className="stat-card accent">
          <span className="stat-number">256</span>
          <span className="stat-label">Courts Available</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">83</span>
          <span className="stat-label">Counties Covered</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">100MB</span>
          <span className="stat-label">Max File Size</span>
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
          <p>File a new document with any Michigan court. Our guided wizard walks you through each step.</p>
          <Link to="/filing/new" className="btn btn-primary">Start Filing</Link>
        </div>
        <div className="card">
          <div className="card-icon">&#128196;</div>
          <h3>My Filings</h3>
          <p>View, track, and manage all your submitted filings. See real-time status updates.</p>
          <Link to="/filings" className="btn btn-secondary">View Filings</Link>
        </div>
        <div className="card">
          <div className="card-icon">&#128269;</div>
          <h3>Case Search</h3>
          <p>Search for cases across all Michigan courts by case number or party name.</p>
          <Link to="/cases/search" className="btn btn-secondary">Search Cases</Link>
        </div>
      </div>

      {/* Advantages over MiFILE */}
      <div className="advantages-section">
        <h3>Better Than MiFILE</h3>
        <div className="advantage-grid">
          <div className="advantage">
            <strong>100MB file limit</strong>
            <span>vs MiFILE's 25MB cap</span>
          </div>
          <div className="advantage">
            <strong>Auto-save drafts</strong>
            <span>Never lose your work</span>
          </div>
          <div className="advantage">
            <strong>Court rules guidance</strong>
            <span>Know what's required before you file</span>
          </div>
          <div className="advantage">
            <strong>Pre-submission validation</strong>
            <span>Catch errors before clerk review</span>
          </div>
          <div className="advantage">
            <strong>Unified trial + appellate</strong>
            <span>One system for all courts</span>
          </div>
          <div className="advantage">
            <strong>Permanent document storage</strong>
            <span>Your filings are always accessible</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function App() {
  return (
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
            <Route path="/favorites" element={<Favorites />} />
            <Route path="/clerk/queue" element={<ReviewQueue />} />
          </Routes>
        </main>
      </div>
      <Footer />
    </div>
  );
}

export default App;
