import { Routes, Route } from 'react-router-dom';
import Header from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import Footer from './components/layout/Footer';
import FilingWizard from './components/filing/FilingWizard';
import ReviewQueue from './components/clerk/ReviewQueue';
import CaseSearch from './components/search/CaseSearch';

function Dashboard() {
  return (
    <div className="dashboard">
      <h2>Welcome to Michigan Unified E-Filing System</h2>
      <div className="dashboard-cards">
        <div className="card">
          <h3>New Filing</h3>
          <p>File a new document with any Michigan court</p>
          <a href="/filing/new" className="btn btn-primary">Start Filing</a>
        </div>
        <div className="card">
          <h3>My Filings</h3>
          <p>View and manage your submitted filings</p>
          <a href="/filings" className="btn btn-secondary">View Filings</a>
        </div>
        <div className="card">
          <h3>Case Search</h3>
          <p>Search for cases across Michigan courts</p>
          <a href="/cases/search" className="btn btn-secondary">Search Cases</a>
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
            <Route path="/cases/search" element={<CaseSearch />} />
            <Route path="/clerk/queue" element={<ReviewQueue />} />
          </Routes>
        </main>
      </div>
      <Footer />
    </div>
  );
}

export default App;
