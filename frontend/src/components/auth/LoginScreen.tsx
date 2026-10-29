import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Scale, ClipboardCheck, UserRound, BookOpen, ShieldCheck } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { isDemoBuild } from '../../config/demoMode';
import MichiganMark from '../common/MichiganMark';
import MifileComparison from '../marketing/MifileComparison';
import {
  accessToken, clearSession, keycloakConfigured,
  oidcSessionExpected, safeLoginReturnPath, SessionChangedError, startKeycloakLogin,
} from '../../auth/keycloak';

export function getDemoRole(): string | null {
  return localStorage.getItem('demo_role');
}

export function hasAdministrationAccess(): boolean {
  return getDemoRole() === 'admin' || localStorage.getItem('administration_access') === 'true';
}

export function hasSession(): boolean {
  return Boolean(accessToken() || (isDemoBuild() && !oidcSessionExpected() && getDemoRole()));
}

export function getDemoCourtId(): number | null {
  const id = localStorage.getItem('demo_court_id');
  return id ? parseInt(id, 10) : null;
}

interface RoleOption {
  role: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

const roles: RoleOption[] = [
  {
    role: 'attorney',
    label: 'Attorney',
    description: 'File on behalf of clients across all Michigan courts',
    icon: Scale,
  },
  {
    role: 'clerk',
    label: 'Court Clerk',
    description: 'Review filings, manage the court queue, process orders',
    icon: ClipboardCheck,
  },
  {
    role: 'srl',
    label: 'Self-Represented Litigant',
    description: 'File your own case with step-by-step, plain-language guidance',
    icon: UserRound,
  },
  {
    role: 'public',
    label: 'Public docket',
    description: 'Search non-sealed cases and read public filings — no sign-in or account needed',
    icon: BookOpen,
  },
  {
    role: 'admin', label: 'System Administrator', icon: ShieldCheck,
    description: 'Provision accounts, manage court access, and inspect retained changes in this demo',
  },
];

export function applyDemoRole(role: string): void {
  clearSession();
  localStorage.setItem('demo_role', role);
  localStorage.setItem('administration_access', String(role === 'admin'));
  if (role === 'clerk') {
    localStorage.setItem('demo_court_id', '3');
  } else {
    localStorage.removeItem('demo_court_id');
  }
}

export type CourtAssignment = { court_id: number; role: string; court_name?: string | null };
export type SessionProfile = {
  user_type: string;
  court_assignments?: CourtAssignment[];
};

const SHELL_ROLE_BY_USER_TYPE: Record<string, string> = {
  attorney: 'attorney',
  clerk: 'clerk',
  judge: 'clerk',
  admin: 'admin',
  self_represented: 'srl',
  public: 'public',
};

export function applySessionFromProfile(profile: SessionProfile): CourtAssignment[] {
  const previousCourt = getDemoCourtId();
  const role = SHELL_ROLE_BY_USER_TYPE[profile.user_type] ?? 'srl';
  localStorage.setItem('demo_role', role);
  localStorage.removeItem('demo_court_id');
  const assignments = profile.court_assignments ?? [];
  localStorage.setItem('administration_access', String(
    role === 'admin' || assignments.some(assignment => assignment.role === 'admin'),
  ));
  const staffCourts = [...new Map(assignments
    .filter(a => ['clerk', 'judge', 'admin'].includes(a.role))
    .map(a => [a.court_id, a])).values()];
  const staff = staffCourts.find(a => a.court_id === previousCourt) ?? staffCourts[0];
  if (staff) {
    localStorage.setItem('demo_court_id', String(staff.court_id));
  }
  return staffCourts;
}

function LoginScreen() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnPath = safeLoginReturnPath(searchParams.get('next'));
  const demo = isDemoBuild();
  const [signingIn, setSigningIn] = useState(false);
  const [signInError, setSignInError] = useState('');
  const restoreAttempted = useRef(false);
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
      <div className="login-container">
        <div className="login-branding">
          <div className="state-seal">
            <MichiganMark size={30} />
            STATE OF MICHIGAN
          </div>
          <h1>Michigan Unified E-Filing System</h1>
          <p className="login-subtitle">{demo ? 'Demo · ' : ''}Statewide Electronic Filing Portal</p>
        </div>

        {demo && <div className="login-cards">
          {roles.map((option) => (
            <div
              key={option.role}
              className="login-card"
            >
              <div className="login-card-icon">
                <option.icon size={26} strokeWidth={1.75} aria-hidden="true" />
              </div>
              <div className="login-card-role">
                {option.label}
              </div>
              <div className="login-card-desc">{option.description}</div>
              <button
                className="btn btn-primary login-card-btn"
                onClick={() => handleSignIn(option)}
                // Four cards share the visible "Sign In"; the name says which role each opens.
                aria-label={option.role === 'public' ? undefined : `Sign in as ${option.label}`}
              >
                {option.role === 'public' ? 'Browse records' : 'Sign In'}
              </button>
            </div>
          ))}
        </div>}

        {keycloakConfigured() && (
          <div className="login-keycloak">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void signIn()}
              disabled={signingIn}
            >
              {signingIn ? 'Connecting to court sign-in…' : 'Sign in with your court account'}
            </button>
            {signInError && <p className="login-message" role="alert">{signInError}</p>}
            {searchParams.get('reason') === 'expired' && <p className="login-message" role="status">Your court sign-in expired. Sign in again to continue. Unsaved filing drafts are still on this device.</p>}
            <p className="login-keycloak-note">
              Use the identity account approved by your court or state.
            </p>
          </div>
        )}

        {!demo && <div className="login-keycloak">
          {!keycloakConfigured() && <p className="login-message" role="alert">Sign-in is not configured for this deployment. Contact the court&apos;s support team.</p>}
          <Link className="btn btn-secondary" to="/cases/search">Browse public records</Link>
        </div>}
        {demo && <MifileComparison variant="login" />}
      </div>
      {isDemoBuild() && (
        <div className="demo-stakeholder-banner demo-stakeholder-banner--login" role="status">
          Demo — not for real filings.
        </div>
      )}
    </div>
  );
}

export default LoginScreen;
