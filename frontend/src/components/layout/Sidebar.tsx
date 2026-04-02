import { useLocation, Link } from 'react-router-dom';

function Sidebar() {
  const location = useLocation();

  const links = [
    { path: '/', label: 'Dashboard' },
    { path: '/filing/new', label: 'New Filing' },
    { path: '/filings', label: 'My Filings' },
    { path: '/cases/search', label: 'Case Search' },
    { path: '/clerk/queue', label: 'Clerk Queue' },
  ];

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
        <p>Courts: 242+</p>
        <p>Counties: 83</p>
        <p>MCR 1.109 Compliant</p>
      </div>
    </aside>
  );
}

export default Sidebar;
