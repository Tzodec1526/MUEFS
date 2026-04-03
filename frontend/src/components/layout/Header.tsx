import { Link, useNavigate } from 'react-router-dom';
import { getDemoRole, getDemoUserName } from '../auth/LoginScreen';

function Header() {
  const navigate = useNavigate();
  const role = getDemoRole();
  const userName = getDemoUserName();

  const handleSwitchRole = () => {
    localStorage.removeItem('demo_role');
    localStorage.removeItem('demo_user_name');
    navigate('/login');
  };

  const roleLabelMap: Record<string, string> = {
    attorney: 'Attorney',
    clerk: 'Court Clerk',
    srl: 'Self-Represented Litigant',
  };

  const roleLabel = role ? roleLabelMap[role] || role : '';

  return (
    <header className="app-header">
      <div className="header-brand">
        <h1>Michigan Unified E-Filing System</h1>
        <span className="header-subtitle">State Court Administrative Office</span>
      </div>
      <nav className="header-nav">
        <Link to="/">Dashboard</Link>
        <Link to="/filing/new">New Filing</Link>
        <Link to="/cases/search">Case Search</Link>
        <Link to="/clerk/queue">Clerk Review</Link>
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
  );
}

export default Header;
