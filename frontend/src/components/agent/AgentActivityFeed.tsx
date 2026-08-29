import { useEffect, useState } from 'react';
import { getAgentActivity, type AgentActivityEntry } from '../../webmcp/activity';

function AgentActivityFeed() {
  const [entries, setEntries] = useState<AgentActivityEntry[]>(() => getAgentActivity());

  useEffect(() => {
    const refresh = () => setEntries(getAgentActivity());
    window.addEventListener('muefs-agent-activity', refresh);
    return () => window.removeEventListener('muefs-agent-activity', refresh);
  }, []);

  if (entries.length === 0) {
    return (
      <p className="agent-activity-empty">
        No agent tool calls yet. Ask your agent to run <code>get_agent_session</code> while this page is open.
      </p>
    );
  }

  return (
    <ol className="agent-activity-list">
      {entries.map((e) => (
        <li key={e.id} className={e.ok ? 'ok' : 'fail'}>
          <span className="agent-activity-tool">{e.tool}</span>
          <span className="agent-activity-meta">
            {e.durationMs}ms · {new Date(e.at).toLocaleTimeString()}
          </span>
          <span className="agent-activity-summary">{e.summary}</span>
        </li>
      ))}
    </ol>
  );
}

export default AgentActivityFeed;
