import { listFilings } from '../../api/filings';
import { getDemoRole } from '../../components/auth/LoginScreen';
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
          suggested_next_tool: suggested,
          human_in_the_loop:
            'Agents may research and navigate; only humans submit filings in the wizard.',
        });
      },
    },
    { signal },
  );
}
