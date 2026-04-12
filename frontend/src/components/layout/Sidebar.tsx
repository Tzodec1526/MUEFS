import { useLocation, Link } from 'react-router-dom';
import { getDemoRole } from '../auth/LoginScreen';

function Sidebar() {
  const location = useLocation();
  const role = getDemoRole();

  const allLinks = [
    { path: '/', label: 'Dashboard', roles: ['attorney', 'clerk', 'srl', 'public'] },
    { path: '/filing/new', label: 'New Filing', roles: ['attorney', 'srl'] },
    { path: '/filings', label: 'My Filings', roles: ['attorney', 'srl'] },
    { path: '/cases/search', label: 'Case Search', roles: ['attorney', 'clerk', 'srl', 'public'] },
    { path: '/favorites', label: 'Favorites', roles: ['attorney', 'srl'] },
    { path: '/clerk/queue', label: 'Review Queue', roles: ['clerk'] },
    { path: '/stats', label: 'Coverage Stats', roles: ['attorney', 'clerk', 'srl', 'public'] },
  ];

  const links = allLinks.filter(link => !role || link.roles.includes(role));

  return (
    <aside className="sidebar">
      <nav>
        <ul>
          {links.map((link) => (
            <li key={link.path}>
              <Link
                to={link.path}
                className={location.pathname === link.path ? 'active' : ''}
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="sidebar-info">
        <h4>Quick Info</h4>
        <p>All Michigan Courts</p>
        <p>All 83 Counties</p>
        <p>MCR 1.109 Compliant</p>
      </div>
    </aside>
  );
}

export default Sidebar;
