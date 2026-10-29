import { getDemoRole } from '../../components/auth/LoginScreen';
import { confirmAgentAction } from '../confirm';
import { DEMO_ROLES, type ToolExecutors } from '../definitions';
import { navigateApp } from '../navigate';
import { toolError, toolOk } from '../output';

/** Demo sign-in tools; their definitions are demoOnly, so other builds never register them. */
export const authTools = {
  async sign_in_demo_role(input) {
    const role = String(input.role);
    if (!DEMO_ROLES.includes(role as (typeof DEMO_ROLES)[number])) {
      return toolError('Invalid role. Use attorney, clerk, srl, public, or admin.', 'invalid');
    }
    const ok = await confirmAgentAction(`Allow the agent to sign in as ${role}?`);
    if (!ok) return toolError('Human declined role switch.', 'needs_confirmation');
    const path = `/login?role=${role}`;
    const result = navigateApp(path);
    if (!result.ok) return toolError(result.error, 'invalid');
    return toolOk({
      role,
      path,
      message: `Navigating to sign in as ${role}.`,
    });
  },

  async get_current_demo_role() {
    const role = getDemoRole();
    const labels: Record<string, string> = {
      attorney: 'Attorney',
      clerk: 'Court Clerk',
      srl: 'Self-Represented Litigant',
      public: 'Public docket viewer',
      admin: 'System Administrator',
    };
    return toolOk({
      role: role || 'anonymous',
      label: role ? labels[role] || role : 'Anonymous public visitor',
    });
  },
} satisfies ToolExecutors;
