import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { isDemoBuild } from '../../config/demoMode';
import MichiganMark from '../common/MichiganMark';
import {
  keycloakConfigured, oidcSessionExpected, safeLoginReturnPath, SessionChangedError, startKeycloakLogin,
} from '../../auth/keycloak';
import { applyDemoRole, hasSession } from '../../auth/session';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

interface RoleOption {
  role: string;
  label: string;
  description: string;
}

const roles: RoleOption[] = [
  { role: 'attorney', label: 'Attorney', description: 'File and track cases for clients' },
  { role: 'clerk', label: 'Court clerk', description: 'Review filings, manage the court queue and process orders' },
  { role: 'srl', label: 'Self-represented litigant', description: 'File your own case with step-by-step guidance' },
  { role: 'public', label: 'Public docket', description: 'Search non-sealed cases and read public filings without an account' },
  { role: 'admin', label: 'System administrator', description: 'Manage accounts, court access and retained changes' },
];

function LoginScreen() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnPath = safeLoginReturnPath(searchParams.get('next'));
  const demo = isDemoBuild();
  const [signingIn, setSigningIn] = useState(false);
  const [signInError, setSignInError] = useState('');
  const restoreAttempted = useRef(false);
  usePageTitle('Sign in');
  const signIn = useCallback(async () => {
    setSigningIn(true);
    setSignInError('');
    try { await startKeycloakLogin(returnPath); }
    catch (error) {
      setSignInError(error instanceof SessionChangedError ? error.message : 'Could not connect to court sign-in. Try again, or contact the court if this continues.');
      setSigningIn(false);
    }
  }, [returnPath]);

  useEffect(() => {
    if (!restoreAttempted.current && oidcSessionExpected() && keycloakConfigured() && !hasSession()) {
      restoreAttempted.current = true;
      void signIn();
    }
  }, [signIn]);

  useEffect(() => {
    const role = searchParams.get('role');
    if (!demo || !role || !roles.some((r) => r.role === role)) return;
    applyDemoRole(role);
    navigate(role === 'public' ? '/cases/search' : returnPath, { replace: true });
  }, [searchParams, navigate, returnPath, demo]);

  const handleSignIn = (option: RoleOption) => {
    applyDemoRole(option.role);
    navigate(option.role === 'public' ? '/cases/search' : returnPath);
  };

  return (
    <div className="login-screen">
      <div className="login-brand">
        <p className="login-product">
          <MichiganMark size={96} />
          Michigan Unified E-Filing System
        </p>
        <p className="login-pitch">
          One portal for filing, clerk review, public case search and document delivery in Michigan courts.
        </p>
        {demo && (
          <p className="login-disclaimer">
            Open-source demo, not for real filings. Not affiliated with SCAO or the Michigan Supreme Court.
          </p>
        )}
      </div>

      <main className="login-main">
        <PageHeading>Sign in</PageHeading>
        {demo && <p className="login-demo-note">Choose a role to explore the demo.</p>}

        {demo && <ul className="login-roles">
          {roles.map((option) => (
            <li key={option.role}>
              <div>
                <strong>{option.label}</strong>
                <span>{option.description}</span>
              </div>
              <button
                className="btn btn-primary btn-small"
                onClick={() => handleSignIn(option)}
                aria-label={option.role === 'public' ? undefined : `Sign in as ${option.label}`}
              >
                {option.role === 'public' ? 'Browse records' : 'Sign in'}
              </button>
            </li>
          ))}
        </ul>}

        {keycloakConfigured() && (
          <div className="login-keycloak">
            {searchParams.get('reason') === 'expired' && <p role="status" className="alert alert-warning">Your court sign-in expired. Sign in again to continue. Unsaved filing drafts are still on this device.</p>}
            {signInError && <p role="alert" className="alert alert-error">{signInError}</p>}
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void signIn()}
              disabled={signingIn}
            >
              {signingIn ? 'Connecting to court sign-in…' : 'Sign in with your court account'}
            </button>
            <p className="login-help">Use the identity account approved by your court or state.</p>
          </div>
        )}

        {!demo && <div className="login-keycloak">
          {!keycloakConfigured() && <p role="alert" className="alert alert-error">Sign-in is not configured for this deployment. Contact the court&apos;s support team.</p>}
          <Link className="btn btn-secondary" to="/cases/search">Browse public records</Link>
        </div>}

        <p className="login-about"><Link to="/about">About MUEFS</Link></p>
      </main>
    </div>
  );
}

export default LoginScreen;
