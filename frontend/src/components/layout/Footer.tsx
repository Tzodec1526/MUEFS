function Footer() {
  return (
    <footer className="app-footer">
      <p>Michigan Unified E-Filing System (MUEFS) v0.1.0</p>
      <p>State Court Administrative Office | Michigan Supreme Court</p>
      <p>
        <a href="https://courts.michigan.gov" target="_blank" rel="noopener noreferrer">
          Michigan Courts
        </a>
        {' | '}
        <a href="http://localhost:8000/docs" target="_blank" rel="noopener noreferrer">
          API Documentation
        </a>
      </p>
    </footer>
  );
}

export default Footer;
