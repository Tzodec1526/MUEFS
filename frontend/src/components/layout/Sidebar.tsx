import { useLocation } from 'react-router-dom';

function Sidebar() {
  const location = useLocation();

  const links = [
    { path: '/', label: 'Dashboard', icon: 'home' },
    { path: '/filing/new', label: 'New Filing', icon: 'file-plus' },
    { path: '/filings', label: 'My Filings', icon: 'files' },
    { path: '/cases/search', label: 'Case Search', icon: 'search' },
    { path: '/clerk/queue', label: 'Clerk Queue', icon: 'inbox' },
  ];

  return (
    <aside className="sidebar">
      <nav>
        <ul>
          {links.map((link) => (
            <li key={link.path}>
              <a
                href={link.path}
                className={location.pathname === link.path ? 'active' : ''}
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div className="sidebar-info">
        <h4>Quick Info</h4>
        <p>Courts: 242+</p>
        <p>Counties: 83</p>
        <p>MCR 1.109 Compliant</p>
      </div>
    </aside>
  );
}

export default Sidebar;
