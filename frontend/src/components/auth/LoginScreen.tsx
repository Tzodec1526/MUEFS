import { Link, useNavigate } from 'react-router-dom';
import { isDemoBuild } from '../../config/demoMode';

export function getDemoRole(): string | null {
  return localStorage.getItem('demo_role');
}

export function getDemoUserName(): string | null {
  return localStorage.getItem('demo_user_name');
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
  name: string;
  detail: string;
  description: string;
  icon: string;
}

const roles: RoleOption[] = [
  {
    role: 'attorney',
    name: 'Jane Doe, Esq. (P12345)',
    detail: 'Doe & Associates PLLC',
    description: 'File on behalf of clients across all Michigan courts',
    icon: '\u2696',
  },
  {
    role: 'clerk',
    name: 'Robert Johnson',
    detail: '3rd Circuit Court \u2014 Wayne County',
    description: 'Review filings, manage court queue, process orders',
    icon: '\uD83D\uDCCB',
  },
  {
    role: 'srl',
    name: 'Maria Williams',
    detail: 'Filing without an attorney',
    description: 'Guided filing with plain-language assistance',
    icon: '\uD83D\uDC64',
  },
];

function LoginScreen() {
  const navigate = useNavigate();

  const handleSignIn = (option: RoleOption) => {
    localStorage.setItem('demo_role', option.role);
    localStorage.setItem('demo_user_name', option.name);
    if (option.role === 'clerk') {
      localStorage.setItem('demo_court_id', '3');
      localStorage.setItem('demo_court_name', '3rd Circuit Court - Wayne County');
    } else {
      localStorage.removeItem('demo_court_id');
      localStorage.removeItem('demo_court_name');
    }
    navigate('/');
  };

  return (
    <div className="login-screen">
      {isDemoBuild() && (
        <div className="demo-stakeholder-banner demo-stakeholder-banner--login" role="status">
          <strong>Stakeholder demo</strong>
          {' — '}Pick a role below. No passwords; this is a guided product walkthrough.
        </div>
      )}
      <div className="login-container">
        <div className="login-branding">
          <div className="state-seal">
            <svg className="michigan-outline" viewBox="730 175 155 130" width="32" height="28" aria-label="Michigan outline">
              <path d="M755.6,182.1l1.8-2.1l2.2-0.8l5.4-3.9l2.3-0.6l0.5,0.5l-5.1,5.1l-3.3,1.9l-2.1,0.9L755.6,182.1z M741.5,211.2l0.7-0.6l2.7-0.8l3.6-2.3v-1l0.6-0.6l6-1l2.4-1.9l4.4-2.1l0.2-1.3l1.9-2.9l1.8-0.8l1.3-1.8l2.3-2.3l4.4-2.4l4.7-0.5l1.1,1.1l-0.3,1l-3.7,1l-1.5,3.1l-2.3,0.8l-0.5,2.4l-2.4,3.2l-0.3,2.6l0.8,0.5l1-1.1l3.6-2.9l1.3,1.3h2.3l3.2,1l1.5,1.1l1.5,3.1l2.7,2.7l3.9-0.2l1.5-1l1.6,1.3l1.6,0.5l1.3-0.8h1.1l1.6-1l4-3.6l3.4-1.1l6.6-0.3l4.5-1.9l2.6-1.3l1.5,0.2v5.7l0.5,0.3l2.9,0.8l1.9-0.5l6.1-1.6l1.1-1.1l1.5,0.5v7l3.2,3.1l1.3,0.6l1.3,1l-1.3,0.3l-0.8-0.3l-3.7-0.5l-2.1,0.6l-2.3-0.2l-3.2,1.5h-1.8l-5.8-1.3l-5.2,0.2l-1.9,2.6l-7,0.6l-2.4,0.8l-1.1,3.1l-1.3,1.1l-0.5-0.2l-1.5-1.6l-4.5,2.4h-0.6l-1.1-1.6l-0.8,0.2l-1.9,4.4l-1,4l-3.2,7l-1.2-1l-1.4-1l-1.9-10.3l-3.5-1.4l-2.1-2.3l-12.1-2.7l-2.9-1l-8.2-2.2l-7.9-1.1L741.5,211.2z" fill="currentColor"/>
            </svg>
            STATE OF MICHIGAN
            <svg className="michigan-outline" viewBox="810 210 75 100" width="20" height="28" aria-label="Michigan outline">
              <path d="M841.8,214.2l0.6,2.5l3.2,0.2l1.3-1.2c0,0-0.1-1.5-0.4-1.6c-0.3-0.2-1.6-1.9-1.6-1.9l-2.2,0.2l-1.6,0.2l-0.3,1.1L841.8,214.2z M871.9,277.2l-3.2-8.2l-2.3-9.1l-2.4-3.2l-2.6-1.8l-1.6,1.1l-3.9,1.8l-1.9,5l-2.7,3.7l-1.1,0.6l-1.5-0.6c0,0-2.6-1.5-2.4-2.1c0.2-0.6,0.5-5,0.5-5l3.4-1.3l0.8-3.4l0.6-2.6l2.4-1.6l-0.3-10l-1.6-2.3l-1.3-0.8l-0.8-2.1l0.8-0.8l1.6,0.3l0.2-1.6L850,231l-1.3-2.6h-2.6l-4.5-1.5l-5.5-3.4h-2.7l-0.6,0.6l-1-0.5l-3.1-2.3l-2.9,1.8l-2.9,2.3l0.3,3.6l1,0.3l2.1,0.5l0.5,0.8l-2.6,0.8l-2.6,0.3l-1.5,1.8l-0.3,2.1l0.3,1.6l0.3,5.5l-3.6,2.1l-0.6-0.2v-4.2l1.3-2.4l0.6-2.4l-0.8-0.8l-1.9,0.8l-1,4.2l-2.7,1.1l-1.8,1.9l-0.2,1l0.6,0.8l-0.6,2.6l-2.3,0.5v1.1l0.8,2.4l-1.1,6.1l-1.6,4l0.6,4.7l0.5,1.1l-0.8,2.4l-0.3,0.8l-0.3,2.7l3.6,6l2.9,6.5l1.5,4.8l-0.8,4.7l-1,6l-2.4,5.2l-0.3,2.7l-3.3,3.1l4.4-0.2l21.4-2.3l7.3-1l0.1,1.7l6.9-1.2l10.3-1.5l3.9-0.5l0.1-0.6l0.2-1.5l2.1-3.7l2-1.7l-0.2-5.1l1.6-1.6l1.1-0.3l0.2-3.6l1.5-3l1.1,0.6l0.2,0.6l0.8,0.2l1.9-1L871.9,277.2z" fill="currentColor"/>
            </svg>
          </div>
          <h1>Michigan Unified E-Filing System</h1>
          <p className="login-subtitle">Statewide Electronic Filing Portal</p>
        </div>

        <div className="login-cards">
          {roles.map((option) => (
            <div
              key={option.role}
              className="login-card"
            >
              <div className="login-card-icon">{option.icon}</div>
              <div className="login-card-role">
                {option.role === 'attorney' && 'Attorney'}
                {option.role === 'clerk' && 'Court Clerk'}
                {option.role === 'srl' && 'Self-Represented Litigant'}
              </div>
              <div className="login-card-name">{option.name}</div>
              <div className="login-card-detail">{option.detail}</div>
              <div className="login-card-desc">{option.description}</div>
              <button
                className="btn btn-primary login-card-btn"
                onClick={() => handleSignIn(option)}
              >
                Sign In
              </button>
            </div>
          ))}
        </div>

        <div className="login-public-access">
          <p className="login-public-note">
            Case search requires an authenticated session (court privacy). Select a role below, then use Search.
          </p>
          <Link to="/cases/search" className="btn btn-secondary">
            Search Court Records
          </Link>
        </div>

        <div className="login-footer-note">
          Demo Mode &mdash; Select a role to explore the system (set VITE_ALLOW_DEMO_MODE=true with ALLOW_DEMO_MODE=true)
        </div>
      </div>
    </div>
  );
}

export default LoginScreen;
