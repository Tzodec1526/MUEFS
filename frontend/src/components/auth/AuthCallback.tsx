import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { clearSession, handleKeycloakCallback, SessionChangedError, sessionSnapshot } from '../../auth/keycloak';
import { applySessionFromProfile } from '../../auth/session';
import { apiClient } from '../../api/client';
import { errorMessage } from '../../utils/errors';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

function AuthCallback() {
  const navigate = useNavigate();
  const [error, setError] = useState('');
  usePageTitle(error ? 'Sign-in not completed' : 'Completing sign-in');

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
        <main className="login-container">
          <div className="login-heading"><PageHeading>Sign-in not completed</PageHeading></div>
          <p className="login-message" role="alert">{error}</p>
          <button type="button" className="btn btn-primary" onClick={() => navigate('/login')}>
            Back to login
          </button>
        </main>
      </div>
    );
  }

  return (
    <div className="login-screen">
      <main className="login-container">
        <div className="login-heading"><PageHeading>Completing sign-in</PageHeading></div>
        <p className="login-message" role="status">Completing sign-in…</p>
      </main>
    </div>
  );
}

export default AuthCallback;
