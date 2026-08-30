import { getDemoRole } from '../../components/auth/LoginScreen';
import { isDemoBuild } from '../../config/demoMode';
import { MUTATING, READ_ONLY } from '../annotations';
import { confirmAgentAction, wantsConfirmation } from '../confirm';
import { navigateApp } from '../navigate';
import { toolError, toolOk } from '../output';
import type { ModelContext } from '../types';

const VALID_ROLES = ['attorney', 'clerk', 'srl', 'public'] as const;

export async function registerAuthTools(mc: ModelContext, signal?: AbortSignal): Promise<void> {
  if (!isDemoBuild()) return;

  await mc.registerTool(
    {
      name: 'sign_in_demo_role',
      title: 'Sign in (demo role)',
      description:
        'Switch the demonstration role. Navigates to login and sets attorney, clerk, srl ' +
        '(self-represented), or public. Mutating: ask the human, or pass confirmed=true.',
      inputSchema: {
        type: 'object',
        required: ['role'],
        properties: {
          role: {
            type: 'string',
            enum: [...VALID_ROLES],
            description: 'Demo role to activate',
          },
          confirmed: {
            type: 'boolean',
            description: 'Set true after the human confirms the role switch',
          },
        },
      },
      annotations: MUTATING,
      async execute(input) {
        const role = String(input.role);
        if (!VALID_ROLES.includes(role as (typeof VALID_ROLES)[number])) {
          return toolError('Invalid role. Use attorney, clerk, srl, or public.');
        }
        if (wantsConfirmation(input)) {
          const ok = await confirmAgentAction(`Allow the agent to sign in as ${role}?`);
          if (!ok) return toolError('Human declined role switch.', 'needs_confirmation');
        }
        const path = `/login?role=${role}`;
        const result = navigateApp(path);
        if (!result.ok) return toolError(result.error);
        return toolOk({
          role,
          path,
          message: `Navigating to sign in as ${role}.`,
        });
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'get_current_demo_role',
      title: 'Current demo session role',
      description: 'Return the active demonstration role for this browser session (demo builds only).',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_ONLY,
      async execute() {
        const role = getDemoRole();
        const labels: Record<string, string> = {
          attorney: 'Attorney',
          clerk: 'Court Clerk',
          srl: 'Self-Represented Litigant',
          public: 'Public docket viewer',
        };
        return toolOk({
          role: role || 'anonymous',
          label: role ? labels[role] || role : 'Anonymous public visitor',
        });
      },
    },
    { signal },
  );
}
