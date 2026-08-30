import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bot } from 'lucide-react';
import { webMcpStatus } from '../../webmcp';

/** Header entry to /agent — only when WebMCP is present in this browser. */
function WebMcpHeaderLink() {
  const [available, setAvailable] = useState(() => webMcpStatus().available);
  const [toolCount, setToolCount] = useState(() => webMcpStatus().toolCount);

  useEffect(() => {
    const refresh = () => {
      const s = webMcpStatus();
      setAvailable(s.available);
      setToolCount(s.toolCount);
    };
    refresh();
    window.addEventListener('muefs-webmcp-tools-changed', refresh);
    window.addEventListener('muefs-demo-role-changed', refresh);
    return () => {
      window.removeEventListener('muefs-webmcp-tools-changed', refresh);
      window.removeEventListener('muefs-demo-role-changed', refresh);
    };
  }, []);

  if (!available) return null;

  return (
    <Link to="/agent" className="header-webmcp-link" title="Agent Hub">
      <Bot size={16} aria-hidden />
      <span>Agent</span>
      <span className="header-webmcp-count">{toolCount}</span>
    </Link>
  );
}

export default WebMcpHeaderLink;
