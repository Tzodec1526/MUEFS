import { Link } from 'react-router-dom';
import { Bot } from 'lucide-react';
import { webMcpStatus } from '../../webmcp';

function WebMcpHeaderLink() {
  const status = webMcpStatus();

  return (
    <Link to="/agent" className="header-webmcp-link" title="WebMCP Agent Hub">
      <Bot size={16} aria-hidden />
      <span>Agent</span>
      <span className="header-webmcp-count">{status.toolCount}</span>
    </Link>
  );
}

export default WebMcpHeaderLink;
