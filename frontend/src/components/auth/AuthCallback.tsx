import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { handleKeycloakCallback } from '../../auth/keycloakPkce';
import { applySessionFromProfile, notifyDemoRoleChanged } from './LoginScreen';
import { apiClient } from '../../api/client';

function AuthCallback() {
  const navigate = useNavigate();
  const [error, setError] = useState(false);

  useEffect(() => {
    handleKeycloakCallback(window.location.search)
      .then(async (result) => {
        if (result !== 'ok') {
          setError(true);
          return;
        }
        try {
          const { data } = await apiClient.get('/auth/me');
          applySessionFromProfile(data);
        } catch {
          notifyDemoRoleChanged();
        }
        navigate('/', { replace: true });
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
