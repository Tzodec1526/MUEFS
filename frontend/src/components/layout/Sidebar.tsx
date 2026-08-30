import { useEffect, useState } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { LayoutDashboard, FilePlus2, FolderOpen, Search, Star, ClipboardCheck, Bot } from 'lucide-react';
import { webMcpStatus } from '../../webmcp';
import { getDemoRole } from '../auth/LoginScreen';

function Sidebar() {
  const location = useLocation();
  const role = getDemoRole();
  const [webMcpOn, setWebMcpOn] = useState(() => webMcpStatus().available);

  useEffect(() => {
    const refresh = () => setWebMcpOn(webMcpStatus().available);
    refresh();
    window.addEventListener('muefs-webmcp-tools-changed', refresh);
    return () => window.removeEventListener('muefs-webmcp-tools-changed', refresh);
  }, []);

  const allLinks = [
    { path: '/agent', label: 'Agent Hub', icon: Bot, roles: ['attorney', 'clerk', 'srl', 'public'], agentOnly: true },
    { path: '/', label: 'Dashboard', icon: LayoutDashboard, roles: ['attorney', 'clerk', 'srl', 'public'] },
    { path: '/filing/new', label: 'New Filing', icon: FilePlus2, roles: ['attorney', 'srl'] },
    { path: '/filings', label: 'My Filings', icon: FolderOpen, roles: ['attorney', 'srl'] },
    { path: '/cases/search', label: 'Case Search', icon: Search, roles: ['attorney', 'clerk', 'srl', 'public'] },
    { path: '/favorites', label: 'Favorites', icon: Star, roles: ['attorney', 'srl'] },
    { path: '/clerk/queue', label: 'Review Queue', icon: ClipboardCheck, roles: ['clerk'] },
  ];

  const links = allLinks.filter((link) => {
    if (link.agentOnly && !webMcpOn) return false;
    if (!role) return link.path === '/cases/search';
    return link.roles.includes(role);
  });

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
