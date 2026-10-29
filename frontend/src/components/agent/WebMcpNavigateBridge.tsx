import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MUEFS_NAVIGATE_EVENT, setNavigateBridgeArmed } from '../../webmcp/navigate';

/** Routes agent navigate_to calls through the SPA router instead of a full page load. */
function WebMcpNavigateBridge() {
  const navigate = useNavigate();

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

  // Page context for agents comes from get_agent_session; the spec's provideContext() is gone.
  return null;
}

export default WebMcpNavigateBridge;
