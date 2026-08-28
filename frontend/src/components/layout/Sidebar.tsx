import { useLocation, Link } from 'react-router-dom';
import { LayoutDashboard, FilePlus2, FolderOpen, Search, Star, ClipboardCheck, Bot } from 'lucide-react';
import { getDemoRole } from '../auth/LoginScreen';

function Sidebar() {
  const location = useLocation();
  const role = getDemoRole();

  const allLinks = [
    { path: '/agent', label: 'Agent Hub', icon: Bot, roles: ['attorney', 'clerk', 'srl', 'public'] },
    { path: '/', label: 'Dashboard', icon: LayoutDashboard, roles: ['attorney', 'clerk', 'srl', 'public'] },
    { path: '/filing/new', label: 'New Filing', icon: FilePlus2, roles: ['attorney', 'srl'] },
    { path: '/filings', label: 'My Filings', icon: FolderOpen, roles: ['attorney', 'srl'] },
    { path: '/cases/search', label: 'Case Search', icon: Search, roles: ['attorney', 'clerk', 'srl', 'public'] },
    { path: '/favorites', label: 'Favorites', icon: Star, roles: ['attorney', 'srl'] },
    { path: '/clerk/queue', label: 'Review Queue', icon: ClipboardCheck, roles: ['clerk'] },
  ];

  // Guests (no role) see only the public docket routes; signed-in roles see their own set.
  const links = allLinks.filter(link =>
    role ? link.roles.includes(role) : link.path === '/cases/search' || link.path === '/agent'
  );

  return (
    <aside className="sidebar">
      <nav>
        <ul>
          {links.map((link) => (
            <li key={link.path}>
              <Link
                to={link.path}
                className={(link.path === '/' ? location.pathname === '/' : location.pathname.startsWith(link.path)) ? 'active' : ''}
              >
                <link.icon size={17} strokeWidth={2} aria-hidden="true" />
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="sidebar-info">
        <h4>Quick Info</h4>
        <p>Trial, Appellate &amp; Specialized Courts</p>
        <p>All 83 Counties</p>
        <p>MCR 1.109 Compliant</p>
      </div>
    </aside>
  );
}

export default Sidebar;
