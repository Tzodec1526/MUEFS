import { useNavigate } from 'react-router-dom';
import { Scale, ClipboardCheck, UserRound, BookOpen, Bot } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { isDemoBuild } from '../../config/demoMode';
import MichiganMark from '../common/MichiganMark';
import MifileComparison from '../marketing/MifileComparison';
import { keycloakConfigured, startKeycloakLogin } from '../../auth/keycloakPkce';

export function getDemoRole(): string | null {
  return localStorage.getItem('demo_role');
}

export function getDemoCourtId(): number | null {
  const id = localStorage.getItem('demo_court_id');
  return id ? parseInt(id, 10) : null;
}

export function getDemoCourtName(): string | null {
  return localStorage.getItem('demo_court_name');
}

interface RoleOption {
  role: string;
  description: string;
  icon: LucideIcon;
}

const roles: RoleOption[] = [
  {
    role: 'attorney',
    description: 'File on behalf of clients across all Michigan courts',
    icon: Scale,
  },
  {
    role: 'clerk',
    description: 'Review filings, manage the court queue, process orders',
    icon: ClipboardCheck,
  },
  {
    role: 'srl',
    description: 'File your own case with step-by-step, plain-language guidance',
    icon: UserRound,
  },
  {
    role: 'public',
    description: 'Search non-sealed cases and read public filings — no sign-in or account needed',
    icon: BookOpen,
  },
];

function LoginScreen() {
  const navigate = useNavigate();

  const handleSignIn = (option: RoleOption) => {
    localStorage.setItem('demo_role', option.role);
    if (option.role === 'clerk') {
      localStorage.setItem('demo_court_id', '3');
      localStorage.setItem('demo_court_name', '3rd Circuit Court - Wayne County');
    } else {
      localStorage.removeItem('demo_court_id');
      localStorage.removeItem('demo_court_name');
    }
    navigate(option.role === 'public' ? '/cases/search' : '/');
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
          <p className="login-subtitle">Demo &middot; Statewide Electronic Filing Portal</p>
        </div>

        <div className="login-cards">
          {roles.map((option) => (
            <div
              key={option.role}
              className="login-card"
            >
              <div className="login-card-icon">
                <option.icon size={26} strokeWidth={1.75} aria-hidden="true" />
              </div>
              <div className="login-card-role">
                {option.role === 'attorney' && 'Attorney'}
                {option.role === 'clerk' && 'Court Clerk'}
                {option.role === 'srl' && 'Self-Represented Litigant'}
                {option.role === 'public' && 'Public docket'}
              </div>
              <div className="login-card-desc">{option.description}</div>
              <button
                className="btn btn-primary login-card-btn"
                onClick={() => handleSignIn(option)}
              >
                {option.role === 'public' ? 'Browse records' : 'Sign In'}
              </button>
            </div>
          ))}
        </div>

        {keycloakConfigured() && (
          <div className="login-keycloak">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => startKeycloakLogin()}
            >
              Sign in with Keycloak (PKCE)
            </button>
            <p className="login-keycloak-note">
              Production identity provider — uses authorization code + PKCE when configured.
            </p>
          </div>
        )}

        <MifileComparison variant="login" />

        {isDemoBuild() && (
          <div className="login-webmcp-hint">
            <Bot size={18} aria-hidden="true" />
            <span>
              <strong>Agent-ready:</strong> enable{' '}
              <code>chrome://flags/#enable-webmcp-testing</code> to expose case search and
              filing tools to browser AI agents (WebMCP).
            </span>
          </div>
        )}
      </div>
      {isDemoBuild() && (
        <div className="demo-stakeholder-banner demo-stakeholder-banner--login" role="status">
          <strong>Interactive demo</strong>
          {' — '}pick a role to explore the system. No accounts, no passwords.
        </div>
      )}
    </div>
  );
}

export default LoginScreen;
