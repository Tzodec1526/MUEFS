import { getDemoRole } from '../components/auth/LoginScreen';
import { catalogForRole } from './catalog';
import type { ModelContext } from './types';

export interface AgentPageContext {
  role: string;
  path: string;
  tool_count: number;
  suggested_next_tool: string;
  agent_hub: string;
}

export function buildAgentPageContext(): AgentPageContext {
  const role = getDemoRole();
  const tools = catalogForRole(role);
  let suggested = 'get_agent_catalog';
  if (!role) suggested = 'sign_in_demo_role';
  else if (role === 'clerk') suggested = 'clerk_triage_workflow';
  else if (role === 'attorney' || role === 'srl') suggested = 'attorney_motion_workflow';

  return {
    role: role || 'anonymous',
    path: typeof window !== 'undefined' ? window.location.pathname + window.location.search : '/',
    tool_count: tools.length,
    suggested_next_tool: suggested,
    agent_hub: '/agent',
  };
}

export function publishAgentPageContext(mc?: ModelContext | null): void {
  const host = mc ?? (typeof document !== 'undefined' ? document.modelContext : undefined);
  if (!host?.provideContext) return;
  try {
    void host.provideContext({ ...buildAgentPageContext() });
  } catch {
    /* host optional */
  }
}
