import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { handleKeycloakCallback } from '../../auth/keycloakPkce';
import { applySessionFromProfile, notifyDemoRoleChanged } from './LoginScreen';
import { apiClient } from '../../api/client';
import { getErrorDetail } from '../../utils/errors';

function AuthCallback() {
  const navigate = useNavigate();
  const [error, setError] = useState('');

  useEffect(() => {
    handleKeycloakCallback(window.location.search)
      .then(async (returnPath) => {
        if (!returnPath) {
          setError('Sign-in failed. Return to the login page and try again.');
          return;
        }
        try {
          const { data } = await apiClient.get('/auth/me');
          applySessionFromProfile(data);
        } catch (err) {
          localStorage.removeItem('auth_token');
          setError(getErrorDetail(err) || 'Could not verify your court account. Return to the login page and try again.');
          notifyDemoRoleChanged();
          return;
        }
        navigate(returnPath, { replace: true });
      })
      .catch(() => setError('Sign-in failed. Return to the login page and try again.'));
  }, [navigate]);

  if (error) {
    return (
      <div className="login-screen">
        <div className="login-container">
          <p role="alert">{error}</p>
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
