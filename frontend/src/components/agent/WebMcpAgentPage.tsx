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

const EXAMPLE_PROMPTS = [
  {
    title: 'Session',
    prompt:
      'Call get_challenge_briefing, then get_agent_session and get_agent_catalog.',
    tools: ['get_challenge_briefing', 'get_agent_session', 'get_agent_catalog'],
  },
  {
    title: 'Attorney motion',
    prompt:
      'Sign in as attorney, run attorney_motion_workflow for party Smith, navigate_to the filing wizard, then call get_agent_activity.',
    tools: ['sign_in_demo_role', 'attorney_motion_workflow', 'navigate_to', 'get_agent_activity'],
  },
  {
    title: 'SRL MCR',
    prompt:
      'Sign in as srl. Run explain_mcr_for_filing for court_id 3 case_type_id 35 filing_type motion.',
    tools: ['sign_in_demo_role', 'explain_mcr_for_filing'],
  },
  {
    title: 'Clerk triage',
    prompt:
      'Sign in as clerk, run clerk_triage_workflow, then navigate_to /clerk/queue.',
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
      pushToast('Copied', 'success');
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
            {tools.length} tools · {role || 'anonymous'}
          </p>
          <nav className="agent-hub-nav" aria-label="Agent hub">
            <Link to="/login">Sign in</Link>
            <Link to="/cases/search">Case search</Link>
            <Link to="/">App home</Link>
            <a href="https://github.com/Tzodec1526/MUEFS" target="_blank" rel="noreferrer">
              Source
            </a>
          </nav>
        </div>
      </header>

      <section className="agent-hub-status" aria-live="polite">
        <h2>WebMCP</h2>
        <p className={`agent-status-pill ${status.available ? 'ok' : 'off'}`}>
          {status.available ? (
            <>
              <CheckCircle2 size={18} aria-hidden /> {status.toolCount} registered
            </>
          ) : (
            <>
              <XCircle size={18} aria-hidden /> Unavailable
            </>
          )}
        </p>
        {browserTools.length > 0 && (
          <p className="agent-browser-tools">
            <code>getTools()</code>: {browserTools.length}
          </p>
        )}
        <p>
          <Link to="/login">Switch role</Link>
          {' · '}
          <Link to="/cases/search">Case search</Link>
        </p>
      </section>

      <section className="agent-hub-activity">
        <h2>Activity</h2>
        <AgentActivityFeed />
      </section>

      <AgentDeclarativeSearch />

      <FlagshipDemoRunner />

      <section className="agent-hub-workflows">
        <h2>Workflows</h2>
        <div className="agent-workflow-grid">
          {workflows.map((t) => (
            <article key={t.name} className="agent-workflow-card">
              <code>{t.name}</code>
              <h3>{t.title}</h3>
            </article>
          ))}
        </div>
      </section>

      <section className="agent-hub-tools">
        <h2>
          <Bot size={20} aria-hidden /> Discovery
        </h2>
        <ul className="agent-tool-list">
          {discovery.map((t) => (
            <li key={t.name}>
              <code>{t.name}</code>
              <span>{t.title}</span>
              {t.readOnly && <span className="agent-tag">read-only</span>}
            </li>
          ))}
        </ul>
      </section>

      {actions.length > 0 && (
        <section className="agent-hub-tools">
          <h2>Actions</h2>
          <ul className="agent-tool-list">
            {actions.map((t) => (
              <li key={t.name}>
                <code>{t.name}</code>
                <span>{t.title}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="agent-hub-prompts">
        <h2>Prompts</h2>
        {EXAMPLE_PROMPTS.map((item) => (
          <article key={item.title} className="agent-prompt-card">
            <div className="agent-prompt-header">
              <h3>{item.title}</h3>
              <button
                type="button"
                className="btn btn-secondary btn-icon"
                onClick={() => handleCopy(item.prompt)}
                title="Copy"
              >
                <Copy size={14} aria-hidden />
                Copy
              </button>
            </div>
            <blockquote>{item.prompt}</blockquote>
          </article>
        ))}
      </section>
    </div>
  );
}

export default WebMcpAgentPage;
