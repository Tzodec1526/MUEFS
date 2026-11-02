import { Link } from 'react-router-dom';

function Footer() {
  return (
    <footer className="app-footer">
      <p>Michigan Unified E-Filing System (MUEFS) v0.1.0</p>
      <p>Open-source e-filing demo. Not affiliated with SCAO or the Michigan Supreme Court.</p>
      <p className="app-footer-links">
        <Link to="/about">About MUEFS</Link>
        <a href="https://courts.michigan.gov" target="_blank" rel="noopener noreferrer">
          Michigan Courts
        </a>
      </p>
    </footer>
  );
}

export default Footer;
