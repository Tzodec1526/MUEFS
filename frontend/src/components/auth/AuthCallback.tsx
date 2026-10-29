import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { clearSession, handleKeycloakCallback, SessionChangedError, sessionSnapshot } from '../../auth/keycloak';
import { applySessionFromProfile } from './LoginScreen';
import { apiClient } from '../../api/client';
import { errorMessage } from '../../utils/errors';

function AuthCallback() {
  const navigate = useNavigate();
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    handleKeycloakCallback()
      .then(async (returnPath) => {
        if (controller.signal.aborted) return;
        if (!returnPath) {
          setError('Sign-in failed. Return to the login page and try again.');
          return;
        }
        const expected = sessionSnapshot();
        try {
          const { data } = await apiClient.get('/auth/me', { signal: controller.signal });
          if (controller.signal.aborted) return;
          applySessionFromProfile(data);
        } catch (err) {
          if (controller.signal.aborted) return;
          clearSession(expected);
          setError(errorMessage(err, 'Could not verify your court account. Return to the login page and try again.'));
          return;
        }
        navigate(returnPath, { replace: true });
      })
      .catch(err => {
        if (!controller.signal.aborted) setError(err instanceof SessionChangedError ? err.message : 'Could not complete court sign-in. Return to the login page and try again.');
      });
    return () => controller.abort();
  }, [navigate]);

  if (error) {
    return (
      <div className="login-screen">
        <div className="login-container">
          <p className="login-message" role="alert">{error}</p>
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
        <p className="login-message" role="status">Completing sign-in…</p>
      </div>
    </div>
  );
}

export default AuthCallback;
