import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { publishAgentPageContext } from '../../webmcp/context';
import { MUEFS_NAVIGATE_EVENT, setNavigateBridgeArmed } from '../../webmcp/navigate';

function WebMcpNavigateBridge() {
  const navigate = useNavigate();

  useEffect(() => {
    setNavigateBridgeArmed(true);
    const onNavigate = (event: Event) => {
      const path = (event as CustomEvent<{ path: string }>).detail?.path;
      if (!path) return;
      navigate(path);
      publishAgentPageContext();
    };
    window.addEventListener(MUEFS_NAVIGATE_EVENT, onNavigate);
    return () => {
      setNavigateBridgeArmed(false);
      window.removeEventListener(MUEFS_NAVIGATE_EVENT, onNavigate);
    };
  }, [navigate]);

  return null;
}

export default WebMcpNavigateBridge;
