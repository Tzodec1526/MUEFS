import { getDemoRole } from '../components/auth/LoginScreen';
import { catalogForBuild, catalogForRole } from './catalog';
import { HUMAN_IN_THE_LOOP, suggestNextStep } from './guidance';

export interface AgentPageContext {
  role: string;
  path: string;
  tool_count: number;
  catalog_size: number;
  /** Null when the human must act first (for example, sign in at /login). */
  suggested_next_tool: string | null;
  next_step: string;
  agent_hub: string;
  human_in_the_loop: string;
  declarative_tools_on_site: string[];
  workflows: string[];
}

/** The current page as agents may see it. */
export function agentVisiblePath(): string {
  if (typeof window === 'undefined') return '/';
  const { pathname, search } = window.location;
  // Sign-in callbacks carry one-time authorization codes in the query.
  return pathname.startsWith('/auth/') ? pathname : pathname + search;
}

export function buildAgentPageContext(): AgentPageContext {
  const role = getDemoRole();
  const tools = catalogForRole(role);
  const path = agentVisiblePath();
  const next = suggestNextStep(role);

  // Form tool names differ from every registered tool's: a host may keep one name map.
  const declarative: string[] = ['search_cases_form'];
  if (path.startsWith('/clerk')) declarative.push('review_queue_form');

  return {
    role: role || 'anonymous',
    path,
    tool_count: tools.length,
    catalog_size: catalogForBuild().length,
    suggested_next_tool: next.tool,
    next_step: next.hint,
    agent_hub: '/agent',
    human_in_the_loop: HUMAN_IN_THE_LOOP,
    declarative_tools_on_site: declarative,
    workflows: tools.filter(t => t.tier === 'workflow').map(t => t.name),
  };
}
