/**
 * Every WebMCP tool MUEFS can register, defined once. The /agent catalog, registration with
 * the browser and the execution-time role check all read this list (see catalog.ts).
 * Implementations live in tools/, keyed by name, so this module stays light for the main bundle.
 */

import { MUTATING, READ_ONLY, UNTRUSTED_RECORDS, type ToolAnnotations } from './annotations';
import type { JsonSchema } from './types';

export type ToolTier = 'discovery' | 'workflow' | 'action';

/**
 * Who may use a tool. `everyone` includes anonymous visitors, public docket viewers and
 * system administrators; administration has no agent tools of its own, and admins are
 * neither filers nor clerks here, matching the filer-only routes in App.tsx.
 */
export type ToolAudience = 'everyone' | 'filer' | 'clerk';

export const AUDIENCE_ROLES: Record<Exclude<ToolAudience, 'everyone'>, readonly string[]> = {
  filer: ['attorney', 'srl'],
  clerk: ['clerk'],
};

export function isFilerRole(role: string | null): boolean {
  return role !== null && AUDIENCE_ROLES.filer.includes(role);
}

export function isClerkRole(role: string | null): boolean {
  return role !== null && AUDIENCE_ROLES.clerk.includes(role);
}

/** Roles the demo sign-in tool can switch to. */
export const DEMO_ROLES = ['attorney', 'clerk', 'srl', 'public', 'admin'] as const;

export interface ToolDefinition<Name extends string = string> {
  name: Name;
  title: string;
  description: string;
  inputSchema: JsonSchema;
  annotations: ToolAnnotations;
  tier: ToolTier;
  audience: ToolAudience;
  /** Registered only in builds with demo sign-in (isDemoBuild()). */
  demoOnly?: boolean;
}

const NO_INPUT = { type: 'object', properties: {} } as const;

/** The largest id or page number the API accepts (PostgreSQL integer). */
const MAX_RECORD_ID = 2_147_483_647;

/**
 * A record id (case, filing, court, case type). Tools put ids into API paths, so the input
 * check (input.ts) must reject anything but an integer in the API's range.
 */
function recordId(description?: string) {
  return { type: 'integer', minimum: 1, maximum: MAX_RECORD_ID, ...(description ? { description } : {}) } as const;
}

const PAGE = { type: 'integer', minimum: 1, maximum: MAX_RECORD_ID, default: 1 } as const;

const DEFINITIONS = [
  {
    name: 'get_agent_catalog',
    title: 'Agent tool catalog',
    description:
      'Return the WebMCP tools registered for this session (they depend on the signed-in role), ' +
      'with workflows, the human-in-the-loop rule and example prompts. ' +
      'Use this first to discover what the human and agent can do together in MUEFS.',
    inputSchema: NO_INPUT,
    annotations: READ_ONLY,
    tier: 'discovery',
    audience: 'everyone',
  },
  {
    name: 'get_agent_session',
    title: 'Agent session context',
    description:
      'Return the current browser session: signed-in role, page path, registered tool count, ' +
      'draft filings for filers, and the suggested next step. ' +
      'Call this at the start of any agent conversation.',
    inputSchema: NO_INPUT,
    annotations: READ_ONLY,
    tier: 'discovery',
    audience: 'everyone',
  },
  {
    name: 'get_agent_activity',
    title: 'Agent activity log',
    description:
      'Return recent WebMCP tool calls from this browser tab (same feed shown on /agent). ' +
      'Use after workflows to summarize what the agent already did for the human.',
    inputSchema: {
      type: 'object',
      properties: {
        limit: { type: 'integer', description: 'Max entries to return (default 15, max 40)' },
      },
    },
    annotations: READ_ONLY,
    tier: 'discovery',
    audience: 'everyone',
  },
  {
    name: 'search_cases',
    title: 'Search Michigan public court records',
    description:
      'Search the statewide public docket by party name and/or case number, optionally within a court. ' +
      'Sealed matters are excluded. Returns case id, number, court, title, status, filing date, and parties.',
    inputSchema: {
      type: 'object',
      properties: {
        party_name: { type: 'string', description: 'Party or litigant name (partial match)' },
        case_number: { type: 'string', description: 'Case number (partial match)' },
        court_id: recordId('Limit results to this court'),
        page: PAGE,
      },
    },
    annotations: UNTRUSTED_RECORDS,
    tier: 'discovery',
    audience: 'everyone',
  },
  {
    name: 'get_case_docket',
    title: 'Open a case docket',
    description:
      'Return public docket details for a case by numeric id (from search_cases). ' +
      'Sealed cases require an authorized account and will return forbidden.',
    inputSchema: {
      type: 'object',
      required: ['case_id'],
      properties: {
        case_id: recordId('Internal case id from search results'),
      },
    },
    annotations: UNTRUSTED_RECORDS,
    tier: 'discovery',
    audience: 'everyone',
  },
  {
    name: 'list_courts',
    title: 'Find Michigan courts',
    description:
      'Search e-filing enabled courts by county name or court name. ' +
      'Use court_id with get_filing_requirements or filing wizard.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'County or court name fragment' },
        page: PAGE,
      },
    },
    annotations: READ_ONLY,
    tier: 'discovery',
    audience: 'everyone',
  },
  {
    name: 'attorney_motion_workflow',
    title: 'Attorney motion workflow',
    description:
      'For an attorney or self-represented filer: find the case (or use case_id), load MCR requirements ' +
      'and motion checklists, count draft filings, and return the pre-filled wizard path with a ' +
      'plain-language plan. Asks the filer to choose when several cases match. Does not submit — ' +
      'the human completes the wizard.',
    inputSchema: {
      type: 'object',
      properties: {
        party_name: { type: 'string' },
        case_number: { type: 'string' },
        case_id: recordId('Explicitly selected case; skips search'),
      },
    },
    annotations: UNTRUSTED_RECORDS,
    tier: 'workflow',
    audience: 'everyone',
  },
  {
    name: 'clerk_triage_workflow',
    title: 'Clerk triage workflow',
    description:
      'Queue counts, oldest pending filings, and navigation to the review UI. Requires clerk role.',
    inputSchema: NO_INPUT,
    annotations: UNTRUSTED_RECORDS,
    tier: 'workflow',
    audience: 'everyone',
  },
  {
    name: 'explain_mcr_for_filing',
    title: 'Explain MCR filing rules',
    description:
      'Plain-language summary of required documents and motion companions for a court/case type. ' +
      'Ideal for self-represented litigants working with an agent.',
    inputSchema: {
      type: 'object',
      required: ['court_id', 'case_type_id'],
      properties: {
        court_id: recordId(),
        case_type_id: recordId(),
        filing_type: { type: 'string', enum: ['initial', 'subsequent', 'motion'] },
      },
    },
    annotations: READ_ONLY,
    tier: 'workflow',
    audience: 'everyone',
  },
  {
    name: 'get_filing_requirements',
    title: 'Filing document requirements',
    description:
      'Return MCR-referenced required and optional documents for a court and case type. ' +
      'Use before uploading in the filing wizard.',
    inputSchema: {
      type: 'object',
      required: ['court_id', 'case_type_id'],
      properties: {
        court_id: recordId(),
        case_type_id: recordId(),
        filing_type: {
          type: 'string',
          enum: ['initial', 'subsequent', 'motion', 'service_only'],
          description: 'Scope requirements to new case vs motion',
        },
      },
    },
    annotations: READ_ONLY,
    tier: 'discovery',
    audience: 'everyone',
  },
  {
    name: 'get_motion_checklists',
    title: 'Motion companion checklists',
    description:
      'MCR 2.119 motion companions (brief, proposed order, proof of service) for a court/case type. ' +
      'Use when advising a filer what to attach to a motion.',
    inputSchema: {
      type: 'object',
      required: ['court_id', 'case_type_id'],
      properties: {
        court_id: recordId(),
        case_type_id: recordId(),
      },
    },
    annotations: READ_ONLY,
    tier: 'discovery',
    audience: 'everyone',
  },
  {
    name: 'navigate_to',
    title: 'Navigate within MUEFS',
    description:
      'Open an in-app path on the same origin. Examples: /cases/search?party=Smith, ' +
      '/filing/new?case_id=1&court_id=3&case_type_id=5, /clerk/queue. ' +
      'The human confirms each navigation in the browser. ' +
      'Does not leave the Michigan e-filing portal.',
    inputSchema: {
      type: 'object',
      required: ['path'],
      properties: {
        path: { type: 'string', description: 'App-relative path starting with /' },
      },
    },
    annotations: MUTATING,
    tier: 'action',
    audience: 'everyone',
  },
  {
    name: 'sign_in_demo_role',
    title: 'Sign in (demo role)',
    description:
      'Switch the demonstration role. Navigates to login and sets attorney, clerk, srl ' +
      '(self-represented), public, or admin. The human confirms the switch in the browser.',
    inputSchema: {
      type: 'object',
      required: ['role'],
      properties: {
        role: { type: 'string', enum: DEMO_ROLES, description: 'Demo role to activate' },
      },
    },
    annotations: MUTATING,
    tier: 'action',
    audience: 'everyone',
    demoOnly: true,
  },
  {
    name: 'get_current_demo_role',
    title: 'Current demo role',
    description: 'Return the active demonstration role for this browser session (demo builds only).',
    inputSchema: NO_INPUT,
    annotations: READ_ONLY,
    tier: 'discovery',
    audience: 'everyone',
    demoOnly: true,
  },
  {
    name: 'list_my_filings',
    title: 'List my e-filings',
    description:
      'List filings for the current signed-in filer (attorney or self-represented). ' +
      'Optional status filter: draft, submitted, under_review, accepted, rejected, returned, ' +
      'or served (service-only records).',
    inputSchema: {
      type: 'object',
      properties: {
        status: {
          type: 'string',
          enum: ['draft', 'submitted', 'under_review', 'accepted', 'rejected', 'returned', 'served'],
        },
        page: PAGE,
      },
    },
    // Case captions and filing descriptions can come from other parties.
    annotations: UNTRUSTED_RECORDS,
    tier: 'discovery',
    audience: 'filer',
  },
  {
    name: 'get_filing_details',
    title: 'Filing details',
    description: 'Return status, documents, and fee waiver state for one of your filings.',
    inputSchema: {
      type: 'object',
      required: ['filing_id'],
      properties: {
        filing_id: recordId(),
      },
    },
    annotations: UNTRUSTED_RECORDS,
    tier: 'discovery',
    audience: 'filer',
  },
  {
    name: 'validate_filing',
    title: 'Validate filing before submit',
    description:
      'Run MCR companion and required-document checks on a draft filing. ' +
      'Returns errors, warnings, and missing required documents.',
    inputSchema: {
      type: 'object',
      required: ['filing_id'],
      properties: {
        filing_id: recordId(),
      },
    },
    // Warnings quote document titles.
    annotations: UNTRUSTED_RECORDS,
    tier: 'workflow',
    audience: 'filer',
  },
  {
    name: 'start_motion_filing',
    title: 'Start a motion filing from a case',
    description:
      'Build the URL to open the filing wizard pre-filled for an existing case (motion or serve-only). ' +
      'Does not submit a filing — returns a path the user or agent can navigate to.',
    inputSchema: {
      type: 'object',
      required: ['case_id', 'court_id', 'case_type_id'],
      properties: {
        case_id: recordId(),
        court_id: recordId(),
        case_type_id: recordId(),
        service_only: { type: 'boolean', default: false },
      },
    },
    annotations: READ_ONLY,
    tier: 'discovery',
    audience: 'filer',
  },
  {
    name: 'get_clerk_review_queue',
    title: 'Clerk review queue',
    description:
      'List filings pending clerk review for the current court. Requires clerk role. ' +
      'Returns envelope id, status, case title, and submitted date.',
    inputSchema: {
      type: 'object',
      properties: {
        page: PAGE,
        status: {
          type: 'string',
          enum: ['all', 'submitted', 'under_review'],
          description: 'Queue filter status',
        },
        search: { type: 'string', maxLength: 200, description: 'Case title, case number, or #filing number' },
        waiting_48h_only: { type: 'boolean', description: 'Only filings received at least 48 hours ago' },
      },
    },
    annotations: UNTRUSTED_RECORDS,
    tier: 'discovery',
    audience: 'clerk',
  },
] as const satisfies readonly ToolDefinition[];

export type ToolName = (typeof DEFINITIONS)[number]['name'];

/** The tools in registration and display order. */
export const TOOL_DEFINITIONS: readonly ToolDefinition<ToolName>[] = DEFINITIONS;

/** Arguments every implementation receives besides the agent's input. */
export interface ToolContext {
  /** The role this registration pass was made for. */
  role: string | null;
}

export type ToolExecutor = (input: Record<string, unknown>, context: ToolContext) => Promise<unknown>;

/** Implementations for some tools, keyed by name; tools/index.ts must cover every name. */
export type ToolExecutors = Partial<Record<ToolName, ToolExecutor>>;
