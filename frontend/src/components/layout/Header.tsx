import { Link, useNavigate } from 'react-router-dom';
import { isDemoBuild } from '../../config/demoMode';
import { getDemoRole, getDemoUserName } from '../auth/LoginScreen';

function Header() {
  const navigate = useNavigate();
  const role = getDemoRole();
  const userName = getDemoUserName();

  const handleSwitchRole = () => {
    localStorage.removeItem('demo_role');
    localStorage.removeItem('demo_user_name');
    localStorage.removeItem('demo_court_id');
    localStorage.removeItem('demo_court_name');
    localStorage.removeItem('muefs_filing_draft');
    localStorage.removeItem('auth_token');
    navigate('/login');
  };

  const roleLabelMap: Record<string, string> = {
    attorney: 'Attorney',
    clerk: 'Court Clerk',
    srl: 'Self-Represented Litigant',
  };

  const roleLabel = role ? roleLabelMap[role] || role : '';

  return (
    <>
      {isDemoBuild() && (
        <div className="demo-stakeholder-banner" role="status" aria-live="polite">
          <span>
            <strong>Demonstration build</strong>
            {' — '}
            Not for filing real cases. Identity and payments are simulated.
          </span>
          <a href="/login" className="demo-banner-link">
            Roles
          </a>
        </div>
      )}
    <header className="app-header">
      <div className="header-brand">
        <h1>Michigan Unified E-Filing System</h1>
        <span className="header-subtitle">Open-Source E-Filing Demo</span>
      </div>
      <nav className="header-nav">
        <Link to="/">Dashboard</Link>
        {role !== 'clerk' && <Link to="/filing/new">New Filing</Link>}
        <Link to="/cases/search">Case Search</Link>
        {role === 'clerk' && <Link to="/clerk/queue">Review Queue</Link>}
      </nav>
      <div className="header-user">
        <span>{userName || 'Guest'}</span>
        {role && (
          <span className={`user-badge ${role === 'srl' ? 'user-badge-srl' : ''}`}>
            {roleLabel}
          </span>
        )}
        <button className="header-switch-role" onClick={handleSwitchRole}>
          Switch Role
        </button>
      </div>
    </header>
    </>
  );
}

export default Header;
