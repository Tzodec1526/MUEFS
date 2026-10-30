import { clearFilingDrafts, hasFilingDrafts } from '../../utils/filingDraft';
import { useContext } from 'react';
import { useNavigate } from 'react-router-dom';
import { isDemoBuild } from '../../config/demoMode';
import { signOut } from '../../auth/keycloak';
import { CourtContext } from '../auth/CourtSession';
import MichiganMark from '../common/MichiganMark';
import NotificationBell from './NotificationBell';

function Header() {
  const navigate = useNavigate();
  const { role } = useContext(CourtContext)!;

  const handleSwitchRole = () => {
    const action = isDemoBuild() ? 'Switching roles' : 'Signing out';
    if (hasFilingDrafts() && !window.confirm(`${action} discards the unsaved filing edits kept in this browser. Continue?`)) return;
    clearFilingDrafts();
    const logoutUrl = signOut();
    if (logoutUrl) window.location.href = logoutUrl;
    else navigate('/login');
  };

  const roleLabelMap: Record<string, string> = {
    attorney: 'Attorney',
    clerk: 'Court clerk',
    srl: 'Self-represented litigant',
    public: 'Public',
    admin: 'System administrator',
  };

  const roleLabel = role ? roleLabelMap[role] || role : '';

  return (
    <>
      {isDemoBuild() && (
        <p className="demo-stakeholder-banner">
          Demo — not for real filings.
          <a href="/login" className="demo-banner-link">
            Roles
          </a>
        </p>
      )}
    <header className="app-header">
      <div className="header-brand">
        <div className="header-seal">
          <MichiganMark size={24} />
        </div>
        <p className="header-title">Michigan Unified E-Filing System</p>
      </div>
      <div className="header-user">
        <NotificationBell />
        {role ? (
          <span className="user-badge">{roleLabel}</span>
        ) : (
          <span>Public visitor</span>
        )}
        {role ? (
          <button className="header-switch-role" onClick={handleSwitchRole}>
            {isDemoBuild() ? 'Switch role' : 'Sign out'}
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
