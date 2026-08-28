import { getDemoRole } from '../components/auth/LoginScreen';
import { catalogForRole } from './catalog';
import type { ModelContext } from './types';

export interface AgentPageContext {
  role: string;
  path: string;
  tool_count: number;
  catalog_size: number;
  suggested_next_tool: string;
  agent_hub: string;
  human_in_the_loop: string;
  declarative_tools_on_site: string[];
  workflows: string[];
}

export function buildAgentPageContext(): AgentPageContext {
  const role = getDemoRole();
  const tools = catalogForRole(role);
  const path =
    typeof window !== 'undefined' ? window.location.pathname + window.location.search : '/';
  let suggested = 'get_agent_catalog';
  if (!role) suggested = 'sign_in_demo_role';
  else if (role === 'clerk') suggested = 'clerk_triage_workflow';
  else if (role === 'attorney' || role === 'srl') suggested = 'attorney_motion_workflow';

  const declarative: string[] = ['search_cases', 'sign_in_demo_role'];
  if (path.startsWith('/clerk')) declarative.push('get_clerk_review_queue');
  if (path.startsWith('/agent')) {
    /* hub also hosts search_cases declarative panel */
  }

  return {
    role: role || 'anonymous',
    path,
    tool_count: tools.length,
    catalog_size: 23,
    suggested_next_tool: suggested,
    agent_hub: '/agent',
    human_in_the_loop:
      'Agents may research and navigate; only humans submit filings in the wizard.',
    declarative_tools_on_site: declarative,
    workflows: [
      'attorney_motion_workflow',
      'clerk_triage_workflow',
      'explain_mcr_for_filing',
      'research_case_for_motion',
    ],
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
