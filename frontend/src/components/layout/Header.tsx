function Header() {
  return (
    <header className="app-header">
      <div className="header-brand">
        <h1>Michigan Unified E-Filing System</h1>
        <span className="header-subtitle">State Court Administrative Office</span>
      </div>
      <nav className="header-nav">
        <a href="/">Dashboard</a>
        <a href="/filing/new">New Filing</a>
        <a href="/cases/search">Case Search</a>
        <a href="/clerk/queue">Clerk Review</a>
      </nav>
      <div className="header-user">
        <span>Demo Attorney</span>
      </div>
    </header>
  );
}

export default Header;
