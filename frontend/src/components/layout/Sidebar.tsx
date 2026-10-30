import { useContext, useId, useState } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { CourtContext } from '../auth/CourtSession';
import { hasAdministrationAccess } from '../../auth/session';

const MAIN_TASK: Record<string, string> = {
  attorney: '/filing/new',
  srl: '/filing/new',
  clerk: '/clerk/queue',
  admin: '/admin',
  public: '/cases/search',
};

function Sidebar() {
  const location = useLocation();
  const { court, courts, role } = useContext(CourtContext)!;
  const [open, setOpen] = useState(false);
  const listId = useId();
  const courtId = court?.court_id;
  const allLinks = [
    { path: '/', label: 'Dashboard', roles: ['attorney', 'clerk', 'srl', 'public'] },
    { path: '/admin', label: 'People & access', roles: ['attorney', 'clerk', 'srl', 'public', 'admin'], adminOnly: true },
    { path: '/filing/new', label: 'New Filing', roles: ['attorney', 'srl'] },
    { path: '/filings', label: 'My Filings', roles: ['attorney', 'srl'] },
    { path: '/clerk/queue', label: 'Review Queue', roles: ['clerk', 'admin'], courtOnly: true },
    { path: '/clerk/fee-reviews', label: 'Fee Reviews', roles: ['clerk', 'admin'], courtOnly: true },
    { path: '/clerk/payment-register', label: 'Receipt Register', roles: ['clerk', 'admin'], courtOnly: true, courtAdminOnly: true },
    { path: '/clerk/cases', label: 'Court Cases', roles: ['clerk', 'admin'], courtOnly: true },
    { path: `/courts/${courtId}/calendar`, label: 'Court Calendar', roles: ['clerk', 'admin'], courtOnly: true },
    { path: `/courts/${courtId}/intake`, label: 'Filing Intake', roles: ['clerk', 'admin'], courtOnly: true },
    { path: '/cases/search', label: 'Case Search', roles: ['attorney', 'clerk', 'srl', 'public', 'admin'] },
    { path: '/favorites', label: 'Favorites', roles: ['attorney', 'srl'] },
    { path: '/notifications', label: 'Notices', roles: ['attorney', 'srl', 'clerk', 'admin'] },
    { path: '/service/deliveries', label: 'Document deliveries', roles: ['attorney', 'srl', 'clerk', 'admin'] },
  ];

  const links = allLinks.filter((link) => {
    if (link.courtAdminOnly && !courts.some(item => item.court_id === courtId && item.role === 'admin')) return false;
    if (link.adminOnly && !hasAdministrationAccess()) return false;
    if (link.courtOnly) return courtId != null;
    if (!role) return link.path === '/cases/search';
    return link.roles.includes(role);
  });
  const mainTask = links.filter(link => link.path === MAIN_TASK[role ?? '']);
  const ordered = [...mainTask, ...links.filter(link => !mainTask.includes(link))];

  return (
    <aside className={`sidebar${open ? ' open' : ''}`}>
      <nav aria-label="Main">
        <ul id={listId}>
          {ordered.map((link) => {
            const active = link.path === '/' ? location.pathname === '/' : location.pathname.startsWith(link.path);
            return (
              <li key={link.path}>
                <Link
                  to={link.path}
                  className={active ? 'active' : ''}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => setOpen(false)}
                >
                  {link.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {ordered.length > 1 && (
        <button
          type="button"
          className="sidebar-toggle"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen(!open)}
        >
          {open ? 'Close menu' : 'Menu'}
        </button>
      )}
    </aside>
  );
}

export default Sidebar;
