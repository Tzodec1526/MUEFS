import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { handleKeycloakCallback } from '../../auth/keycloakPkce';

function AuthCallback() {
  const navigate = useNavigate();
  const [error, setError] = useState(false);

  useEffect(() => {
    handleKeycloakCallback(window.location.search)
      .then((result) => {
        if (result === 'ok') navigate('/', { replace: true });
        else setError(true);
      })
      .catch(() => setError(true));
  }, [navigate]);

  if (error) {
    return (
      <div className="login-screen">
        <div className="login-container">
          <p>Sign-in failed. Return to the login page and try again.</p>
          <button type="button" className="btn btn-primary" onClick={() => navigate('/login')}>
            Back to login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="login-screen">
      <div className="login-container">
        <p>Completing sign-in…</p>
      </div>
    </div>
  );
}

export default AuthCallback;
