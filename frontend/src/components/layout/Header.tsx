import { clearFilingDrafts } from '../../utils/filingDraft';
import { useContext } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { isDemoBuild } from '../../config/demoMode';
import { notifyDemoRoleChanged } from '../auth/LoginScreen';
import { CourtContext } from '../auth/CourtSession';
import MichiganMark from '../common/MichiganMark';
import NotificationBell from './NotificationBell';
import WebMcpHeaderLink from './WebMcpHeaderLink';

function Header() {
  const navigate = useNavigate();
  const { court, role } = useContext(CourtContext)!;

  const handleSwitchRole = () => {
    clearFilingDrafts();
    localStorage.removeItem('demo_role');
    localStorage.removeItem('demo_user_name');
    localStorage.removeItem('demo_court_id');
    localStorage.removeItem('muefs_filing_draft');
    localStorage.removeItem('auth_token');
    localStorage.removeItem('administration_access');
    notifyDemoRoleChanged();
    navigate('/login');
  };

  const roleLabelMap: Record<string, string> = {
    attorney: 'Attorney',
    clerk: 'Court Clerk',
    srl: 'Self-Represented Litigant',
    public: 'Public',
    admin: 'System Administrator',
  };

  const roleLabel = role ? roleLabelMap[role] || role : '';

  return (
    <>
      {isDemoBuild() && (
        <div className="demo-stakeholder-banner" role="status" aria-live="polite">
          <span>Demo — not for real filings.</span>
          <a href="/login" className="demo-banner-link">
            Roles
          </a>
        </div>
      )}
    <header className="app-header">
      <div className="header-brand">
        <div className="header-seal">
          <MichiganMark size={24} />
        </div>
        <div>
          <h1>Michigan Unified E-Filing System</h1>
          <span className="header-subtitle">Statewide Electronic Filing Portal</span>
        </div>
      </div>
      <nav className="header-nav">
        <WebMcpHeaderLink />
        {role && <Link to="/">Dashboard</Link>}
        {(role === 'attorney' || role === 'srl') && <Link to="/filing/new">New Filing</Link>}
        <Link to="/cases/search">Case Search</Link>
        {court && <Link to="/clerk/queue">Review Queue</Link>}
      </nav>
      <div className="header-user">
        <NotificationBell />
        {role ? (
          <span className={`user-badge ${role === 'srl' ? 'user-badge-srl' : ''}`}>
            {roleLabel}
          </span>
        ) : (
          <span>Public visitor</span>
        )}
        {role ? (
          <button className="header-switch-role" onClick={handleSwitchRole}>
            {isDemoBuild() ? 'Switch Role' : 'Sign out'}
          </button>
        ) : (
          <button className="header-switch-role" onClick={() => navigate('/login')}>
            Sign in
          </button>
        )}
      </div>
    </header>
    </>
  );
}

export default Header;
