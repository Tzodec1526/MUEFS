import { listFilings } from '../../api/filings';
import { getDemoRole } from '../../components/auth/LoginScreen';
import { getAgentActivity } from '../activity';
import { catalogForRole } from '../catalog';
import { READ_ONLY } from '../annotations';
import { toolOk } from '../output';
import type { ModelContext } from '../types';

export async function registerSessionTools(mc: ModelContext, signal?: AbortSignal): Promise<void> {
  await mc.registerTool(
    {
      name: 'get_agent_session',
      title: 'Agent session context',
      description:
        'Return the current browser session: demo role, page path, registered tool count, ' +
        'and suggested next tool. Call this at the start of any agent conversation.',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_ONLY,
      async execute() {
        const role = getDemoRole();
        const tools = catalogForRole(role);
        let drafts = 0;
        if (role === 'attorney' || role === 'srl') {
          try {
            const data = await listFilings({ status: 'draft', page: 1 });
            drafts = data.total;
          } catch {
            drafts = 0;
          }
        }

        let suggested = 'get_agent_catalog';
        if (!role) suggested = 'sign_in_demo_role';
        else if (role === 'clerk') suggested = 'clerk_triage_workflow';
        else if (role === 'attorney' || role === 'srl') suggested = 'attorney_motion_workflow';

        return toolOk({
          role: role || 'anonymous',
          path: window.location.pathname + window.location.search,
          origin: window.location.origin,
          tool_count: tools.length,
          draft_filings: drafts,
          agent_hub: '/agent',
          recent_activity_count: getAgentActivity().length,
          suggested_next_tool: suggested,
          human_in_the_loop:
            'Agents may research and navigate; only humans submit filings in the wizard.',
        });
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'get_agent_activity',
      title: 'Agent activity log',
      description:
        'Return recent WebMCP tool calls from this browser tab (same feed shown on /agent). ' +
        'Use after workflows to summarize what the agent already did for the human.',
      inputSchema: {
        type: 'object',
        properties: {
          limit: {
            type: 'integer',
            description: 'Max entries to return (default 15, max 40)',
          },
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        const limit = Math.min(40, Math.max(1, Number(input.limit) || 15));
        const activity = getAgentActivity().slice(0, limit);
        return toolOk({
          count: activity.length,
          activity,
          note: 'Also visible live on /agent for judges and demos.',
        });
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'get_challenge_briefing',
      title: 'WebMCP Challenge briefing',
      description:
        'Judge-oriented overview: why MUEFS fits WebMCP, flagship prompts, live URLs, and ' +
        'human-in-the-loop rules. Call this when evaluating or demoing the challenge entry.',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_ONLY,
      async execute() {
        return toolOk({
          product: 'MUEFS — Michigan Unified E-Filing System',
          challenge: 'OpenAI WebMCP Challenge',
          live_agent_hub: 'https://webmcp.tomcedoz.com/agent',
          canonical_demo: 'https://demo.tomcedoz.com',
          repo: 'https://github.com/Tzodec1526/MUEFS',
          license: 'AGPL-3.0',
          why_webmcp:
            'Court e-filing needs structured docket research, role-aware tools, and MCR checklists — without agents submitting filings.',
          human_in_the_loop: 'Agents research and navigate; only humans click Submit in the filing wizard.',
          apis: {
            imperative: 'document.modelContext.registerTool in frontend/src/webmcp/',
            declarative: ['search_cases', 'sign_in_demo_role', 'get_clerk_review_queue'],
          },
          flagship_prompts: [
            'Call get_agent_session, then get_agent_catalog.',
            'Sign in as attorney, run attorney_motion_workflow for party Smith, then get_agent_activity.',
            'Sign in as clerk, run clerk_triage_workflow, open the review queue.',
            'Sign in as srl, run explain_mcr_for_filing for court_id 3 case_type_id 35 filing_type motion.',
          ],
          suggested_next_tool: 'get_agent_session',
        });
      },
    },
    { signal },
  );
}
