import { Link } from 'react-router-dom';

function Header() {
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
        <span>Demo Attorney</span>
      </div>
    </header>
  );
}

export default Header;
