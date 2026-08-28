import type { ModelContext } from './types';

export interface CatalogEntry {
  name: string;
  title: string;
  description: string;
  readOnly: boolean;
  tier?: 'discovery' | 'workflow' | 'action';
}

export const TOOL_CATALOG: CatalogEntry[] = [
  {
    name: 'get_agent_catalog',
    title: 'Agent tool catalog',
    description: 'List WebMCP tools available in this session (varies by demo role).',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'get_agent_session',
    title: 'Session context',
    description: 'Role, path, draft count, and suggested next tool — start here.',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'get_agent_activity',
    title: 'Agent activity log',
    description: 'Recent WebMCP tool calls in this tab (same feed as /agent).',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'get_challenge_briefing',
    title: 'Challenge briefing',
    description: 'Judge overview: live URLs, flagship prompts, HITL rules, how WebMCP is used.',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'search_cases',
    title: 'Search public docket',
    description: 'Search Michigan public court records by party or case number (declarative form too).',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'get_case_docket',
    title: 'Case docket',
    description: 'Full public docket for a case id from search results.',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'list_courts',
    title: 'Find courts',
    description: 'Search e-filing enabled Michigan courts by county or name.',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'research_case_for_motion',
    title: 'Research case & motion plan',
    description: 'Search → docket → MCR motion checklist → pre-filled filing URL.',
    readOnly: true,
    tier: 'workflow',
  },
  {
    name: 'attorney_motion_workflow',
    title: 'Attorney motion workflow',
    description: 'Full filer plan: case research, requirements, drafts, wizard URL.',
    readOnly: true,
    tier: 'workflow',
  },
  {
    name: 'clerk_triage_workflow',
    title: 'Clerk triage workflow',
    description: 'Queue counts, priority filings, and review plan for court staff.',
    readOnly: true,
    tier: 'workflow',
  },
  {
    name: 'explain_mcr_for_filing',
    title: 'Explain MCR rules',
    description: 'Plain-language required documents and motion companions for SRLs.',
    readOnly: true,
    tier: 'workflow',
  },
  {
    name: 'get_filing_requirements',
    title: 'Filing requirements',
    description: 'MCR-referenced document requirements for a court and case type.',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'get_motion_checklists',
    title: 'Motion checklists',
    description: 'Motion companion documents and MCR guidance (MCR 2.119, etc.).',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'navigate_to',
    title: 'Navigate in app',
    description: 'Open an in-app path (same origin only). Use after sign-in or to show UI.',
    readOnly: false,
    tier: 'action',
  },
  {
    name: 'sign_in_demo_role',
    title: 'Demo sign-in',
    description: 'Switch demo role (attorney, clerk, srl, public) for judge testing.',
    readOnly: false,
    tier: 'action',
  },
  {
    name: 'list_my_filings',
    title: 'My filings',
    description: 'List drafts and submitted filings for the signed-in filer.',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'get_filing_details',
    title: 'Filing details',
    description: 'Status, documents, and validation context for one of your filings.',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'validate_filing',
    title: 'Validate filing',
    description: 'Run MCR companion checks before submit (attorney/SRL).',
    readOnly: true,
    tier: 'workflow',
  },
  {
    name: 'start_motion_filing',
    title: 'Start motion filing',
    description: 'Build URL for wizard pre-filled from an existing case (does not navigate or submit).',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'get_clerk_review_queue',
    title: 'Clerk queue',
    description: 'Filings awaiting clerk review.',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'clerk_queue_summary',
    title: 'Clerk queue summary',
    description: 'Aggregate counts and oldest pending items for clerks.',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'open_filing_for_review',
    title: 'Open filing for review',
    description: 'Deep link into the clerk queue for one filing (human decides accept/reject).',
    readOnly: true,
    tier: 'discovery',
  },
  {
    name: 'get_current_demo_role',
    title: 'Current demo role',
    description: 'Active demonstration role in this browser session.',
    readOnly: true,
    tier: 'discovery',
  },
];

const PUBLIC_TOOLS = new Set([
  'get_agent_catalog',
  'get_agent_session',
  'get_agent_activity',
  'get_challenge_briefing',
  'search_cases',
  'get_case_docket',
  'list_courts',
  'research_case_for_motion',
  'attorney_motion_workflow',
  'clerk_triage_workflow',
  'explain_mcr_for_filing',
  'get_filing_requirements',
  'get_motion_checklists',
  'navigate_to',
  'sign_in_demo_role',
  'get_current_demo_role',
]);

const FILER_TOOLS = new Set([
  ...PUBLIC_TOOLS,
  'list_my_filings',
  'get_filing_details',
  'validate_filing',
  'start_motion_filing',
]);

const CLERK_TOOLS = new Set([
  ...PUBLIC_TOOLS,
  'get_clerk_review_queue',
  'clerk_queue_summary',
  'open_filing_for_review',
]);

export function toolsForRole(role: string | null): Set<string> {
  if (role === 'clerk') return CLERK_TOOLS;
  if (role === 'attorney' || role === 'srl') return FILER_TOOLS;
  return PUBLIC_TOOLS;
}

export function catalogForRole(role: string | null): CatalogEntry[] {
  const allowed = toolsForRole(role);
  return TOOL_CATALOG.filter((t) => allowed.has(t.name));
}

export async function registerCatalogTool(
  mc: ModelContext,
  role: string | null,
  signal?: AbortSignal,
): Promise<void> {
  const entries = catalogForRole(role);
  await mc.registerTool(
    {
      name: 'get_agent_catalog',
      title: 'MUEFS agent tool catalog',
      description:
        'Return the WebMCP tools currently registered for this session. ' +
        'Use this first to discover what the human and agent can do together in MUEFS.',
      inputSchema: { type: 'object', properties: {} },
      annotations: { readOnlyHint: true },
      async execute() {
        return JSON.stringify({
          ok: true,
          role: role || 'anonymous',
          tool_count: entries.length,
          tools: entries,
          workflows: ['attorney_motion_workflow', 'clerk_triage_workflow', 'research_case_for_motion'],
          hint: 'Start with get_agent_session, then attorney_motion_workflow for filers.',
        });
      },
    },
    { signal },
  );
}
