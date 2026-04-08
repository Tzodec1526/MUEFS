import { Link, useNavigate } from 'react-router-dom';

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
      <div className="login-container">
        <div className="login-branding">
          <div className="state-seal">
            <svg className="michigan-outline" viewBox="0 0 100 120" width="28" height="34" aria-label="Michigan outline">
              {/* Upper Peninsula */}
              <path d="M5,35 L12,30 L20,28 L28,25 L35,27 L42,24 L48,26 L52,23 L55,25 L50,30 L45,33 L40,35 L35,34 L30,36 L25,38 L20,37 L15,38 L10,37Z" fill="currentColor"/>
              {/* Lower Peninsula */}
              <path d="M38,42 L45,40 L52,38 L58,40 L65,38 L70,40 L72,45 L74,52 L73,60 L70,68 L68,75 L65,80 L60,85 L55,90 L50,93 L45,90 L40,85 L38,78 L36,70 L35,62 L36,55 L37,48Z" fill="currentColor"/>
            </svg>
            STATE OF MICHIGAN
            <svg className="michigan-outline" viewBox="0 0 100 120" width="28" height="34" aria-label="Michigan outline">
              <path d="M5,35 L12,30 L20,28 L28,25 L35,27 L42,24 L48,26 L52,23 L55,25 L50,30 L45,33 L40,35 L35,34 L30,36 L25,38 L20,37 L15,38 L10,37Z" fill="currentColor"/>
              <path d="M38,42 L45,40 L52,38 L58,40 L65,38 L70,40 L72,45 L74,52 L73,60 L70,68 L68,75 L65,80 L60,85 L55,90 L50,93 L45,90 L40,85 L38,78 L36,70 L35,62 L36,55 L37,48Z" fill="currentColor"/>
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
          <Link to="/cases/search" className="btn btn-secondary">
            Search Court Records
          </Link>
          <span className="login-public-note">No account required</span>
        </div>

        <div className="login-footer-note">
          Demo Mode &mdash; Select a role to explore the system
        </div>
      </div>
    </div>
  );
}

export default LoginScreen;
