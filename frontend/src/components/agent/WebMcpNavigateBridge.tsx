import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { publishAgentPageContext } from '../../webmcp/context';
import { MUEFS_NAVIGATE_EVENT, setNavigateBridgeArmed } from '../../webmcp/navigate';

function WebMcpNavigateBridge() {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    setNavigateBridgeArmed(true);
    const onNavigate = (event: Event) => {
      const path = (event as CustomEvent<{ path: string }>).detail?.path;
      if (!path) return;
      navigate(path);
    };
    window.addEventListener(MUEFS_NAVIGATE_EVENT, onNavigate);
    return () => {
      setNavigateBridgeArmed(false);
      window.removeEventListener(MUEFS_NAVIGATE_EVENT, onNavigate);
    };
  }, [navigate]);

  // Republish provideContext on every SPA route change (links, back/forward, agent navigate).
  useEffect(() => {
    publishAgentPageContext();
  }, [location.pathname, location.search]);

  return null;
}

export default WebMcpNavigateBridge;
