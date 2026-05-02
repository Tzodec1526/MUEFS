import { Link } from 'react-router-dom';

function NotFound() {
  return (
    <div className="not-found">
      <h2>Page not found</h2>
      <p>The page you tried to open doesn’t exist or has moved.</p>
      <Link to="/" className="btn btn-primary">Return to Dashboard</Link>
    </div>
  );
}

export default NotFound;
