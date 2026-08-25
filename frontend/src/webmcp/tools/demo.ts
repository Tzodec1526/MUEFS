import { isDemoBuild } from '../../config/demoMode';
import { getDemoRole } from '../../components/auth/LoginScreen';
import type { ModelContext } from '../types';

const ROLE_LABELS: Record<string, string> = {
  attorney: 'Attorney',
  clerk: 'Court Clerk',
  srl: 'Self-Represented Litigant',
  public: 'Public docket viewer',
};

export async function registerDemoTools(mc: ModelContext, signal?: AbortSignal): Promise<void> {
  if (!isDemoBuild()) return;

  await mc.registerTool(
    {
      name: 'get_current_demo_role',
      title: 'Current demo session role',
      description: 'Return the active demonstration role for this browser session (demo builds only).',
      inputSchema: { type: 'object', properties: {} },
      async execute() {
        const role = getDemoRole();
        return JSON.stringify({
          role: role || 'anonymous',
          label: role ? ROLE_LABELS[role] || role : 'Anonymous public visitor',
        });
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'navigate_to_case_search',
      title: 'Open statewide case search',
      description:
        'Return the URL path for public case search. Does not navigate automatically — ' +
        'the agent should direct the user or use browser navigation.',
      inputSchema: {
        type: 'object',
        properties: {
          party_name: { type: 'string' },
          case_number: { type: 'string' },
        },
      },
      async execute(input) {
        const params = new URLSearchParams();
        if (input.party_name) params.set('party', String(input.party_name));
        if (input.case_number) params.set('case', String(input.case_number));
        const qs = params.toString();
        return JSON.stringify({
          path: `/cases/search${qs ? `?${qs}` : ''}`,
          hint: 'User can open this path in the MUEFS app to run the search.',
        });
      },
    },
    { signal },
  );
}
