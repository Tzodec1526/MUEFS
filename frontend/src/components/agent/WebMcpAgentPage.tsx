import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bot, CheckCircle2, Copy, XCircle } from 'lucide-react';
import {
  catalogForRole,
  listRegisteredToolsFromBrowser,
  webMcpStatus,
} from '../../webmcp';
import { getDemoRole } from '../auth/LoginScreen';
import MichiganMark from '../common/MichiganMark';
import { useToast } from '../common/Toast';
import AgentActivityFeed from './AgentActivityFeed';
import AgentDeclarativeSearch from './AgentDeclarativeSearch';
import FlagshipDemoRunner from './FlagshipDemoRunner';

const JUDGE_PROMPTS = [
  {
    title: 'Session bootstrap',
    prompt:
      'Call get_agent_session, then get_agent_catalog. Summarize what we can do in this Michigan e-filing demo.',
    tools: ['get_agent_session', 'get_agent_catalog'],
  },
  {
    title: 'Attorney motion workflow (flagship)',
    prompt:
      'Sign in as attorney, run attorney_motion_workflow for party Smith, explain the MCR plan in plain language, navigate_to the filing wizard, then call get_agent_activity.',
    tools: ['sign_in_demo_role', 'attorney_motion_workflow', 'navigate_to', 'get_agent_activity'],
  },
  {
    title: 'SRL MCR explainer',
    prompt:
      'Sign in as srl. Run explain_mcr_for_filing for court_id 3 case_type_id 1 filing_type motion. Explain what papers I need in simple terms.',
    tools: ['sign_in_demo_role', 'explain_mcr_for_filing'],
  },
  {
    title: 'Clerk triage workflow',
    prompt:
      'Sign in as clerk, run clerk_triage_workflow, summarize priority filings, and open the review queue.',
    tools: ['sign_in_demo_role', 'clerk_triage_workflow', 'navigate_to'],
  },
];

function copyText(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
}

function WebMcpAgentPage() {
  const status = webMcpStatus();
  const role = getDemoRole();
  const tools = catalogForRole(role);
  const { pushToast } = useToast();
  const [browserTools, setBrowserTools] = useState<string[]>([]);

  useEffect(() => {
    if (!status.available) return;
    listRegisteredToolsFromBrowser().then(setBrowserTools);
    const refresh = () => {
      listRegisteredToolsFromBrowser().then(setBrowserTools);
    };
    window.addEventListener('muefs-webmcp-tools-changed', refresh);
    window.addEventListener('muefs-demo-role-changed', refresh);
    return () => {
      window.removeEventListener('muefs-webmcp-tools-changed', refresh);
      window.removeEventListener('muefs-demo-role-changed', refresh);
    };
  }, [status.available, role]);

  const handleCopy = async (text: string) => {
    try {
      await copyText(text);
      pushToast('Copied to clipboard', 'success');
    } catch {
      pushToast('Could not copy', 'error');
    }
  };

  const workflows = tools.filter((t) => t.tier === 'workflow');
  const discovery = tools.filter((t) => t.tier === 'discovery');
  const actions = tools.filter((t) => t.tier === 'action');

  return (
    <div className="agent-hub-page">
      <header className="agent-hub-header">
        <MichiganMark size={28} />
        <div>
          <h1>MUEFS Agent Hub</h1>
          <p>
            WebMCP Challenge build — {tools.length} tools for this role (15 public · 19 filer · 18 clerk) ·
            declarative forms + imperative workflows
          </p>
          <nav className="agent-hub-nav" aria-label="Agent hub">
            <Link to="/login">Sign in</Link>
            <Link to="/cases/search">Case search</Link>
            <Link to="/">App home</Link>
            <a href="https://github.com/Tzodec1526/MUEFS" target="_blank" rel="noreferrer">
              AGPL repo
            </a>
          </nav>
        </div>
      </header>

      <section className="agent-hub-status" aria-live="polite">
        <h2>WebMCP status</h2>
        <p className={`agent-status-pill ${status.available ? 'ok' : 'off'}`}>
          {status.available ? (
            <>
              <CheckCircle2 size={18} aria-hidden /> Active — {status.toolCount} tools registered
            </>
          ) : (
            <>
              <XCircle size={18} aria-hidden /> Not available in this browser
            </>
          )}
        </p>
        {!status.available && (
          <ol className="agent-setup-steps">
            <li>
              <strong>ChatGPT desktop</strong> in-app browser (WebMCP on by default), or
            </li>
            <li>
              Chrome 149+ → <code>chrome://flags/#enable-webmcp-testing</code> → reload
            </li>
          </ol>
        )}
        {browserTools.length > 0 && (
          <p className="agent-browser-tools">
            Browser <code>getTools()</code>: {browserTools.length} tools visible
          </p>
        )}
        <p>
          Role: <strong>{role || 'anonymous'}</strong>
          {' · '}
          <Link to="/login">Switch role</Link>
          {' · '}
          <Link to="/cases/search">Case search</Link>
        </p>
      </section>

      <section className="agent-hub-activity">
        <h2>Live agent activity</h2>
        <p className="agent-hub-note">Tool calls from this tab appear here as judges test WebMCP.</p>
        <AgentActivityFeed />
      </section>

      <AgentDeclarativeSearch />

      <FlagshipDemoRunner />

      <section className="agent-hub-workflows">
        <h2>Workflow tools</h2>
        <div className="agent-workflow-grid">
          {workflows.map((t) => (
            <article key={t.name} className="agent-workflow-card">
              <code>{t.name}</code>
              <h3>{t.title}</h3>
              <p>{t.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="agent-hub-tools">
        <h2>
          <Bot size={20} aria-hidden /> Discovery tools
        </h2>
        <ul className="agent-tool-list">
          {discovery.map((t) => (
            <li key={t.name}>
              <code>{t.name}</code>
              <span>{t.title}</span>
              <p>{t.description}</p>
              {t.readOnly && <span className="agent-tag">read-only</span>}
            </li>
          ))}
        </ul>
      </section>

      {actions.length > 0 && (
        <section className="agent-hub-tools">
          <h2>Action tools</h2>
          <ul className="agent-tool-list">
            {actions.map((t) => (
              <li key={t.name}>
                <code>{t.name}</code>
                <span>{t.title}</span>
                <p>{t.description}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="agent-hub-prompts">
        <h2>Judge prompts — copy & paste</h2>
        {JUDGE_PROMPTS.map((item) => (
          <article key={item.title} className="agent-prompt-card">
            <div className="agent-prompt-header">
              <h3>{item.title}</h3>
              <button
                type="button"
                className="btn btn-secondary btn-icon"
                onClick={() => handleCopy(item.prompt)}
                title="Copy prompt"
              >
                <Copy size={14} aria-hidden />
                Copy
              </button>
            </div>
            <blockquote>{item.prompt}</blockquote>
            <p className="agent-prompt-tools">
              Tools:{' '}
              {item.tools.map((n) => (
                <code key={n}>{n}</code>
              ))}
            </p>
          </article>
        ))}
      </section>

      <section className="agent-hub-why">
        <h2>Why this wins WebMCP</h2>
        <ul>
          <li>
            <strong>Real domain</strong> — MCR 2.119 motion companions, clerk queues, sealed cases
          </li>
          <li>
            <strong>Human-in-the-loop</strong> — agents research and navigate; humans submit
          </li>
          <li>
            <strong>Hybrid API</strong> — declarative search form on this hub + role-aware imperative tools
          </li>
          <li>
            <strong>Role-aware</strong> — tool set changes when you sign in as filer or clerk
          </li>
        </ul>
        <p>
          <a href="https://github.com/Tzodec1526/MUEFS/blob/main/docs/WEBMCP_CHALLENGE.md" target="_blank" rel="noreferrer">
            Submission guide
          </a>
          {' · '}
          <a href="https://webmcp.devpost.com/" target="_blank" rel="noreferrer">
            Devpost
          </a>
        </p>
      </section>
    </div>
  );
}

export default WebMcpAgentPage;
