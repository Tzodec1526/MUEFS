import { confirmAgentAction } from '../confirm';
import type { ToolExecutors } from '../definitions';
import { isSafeAppPath, navigateApp } from '../navigate';
import { toolError, toolOk } from '../output';

export const navigationTools = {
  async navigate_to(input) {
    const path = typeof input.path === 'string' ? input.path.trim() : '';
    // Ask only about a destination navigateApp would actually open.
    if (!path.startsWith('/') || !isSafeAppPath(path)) {
      return toolError('Path must be an in-app path such as /cases/search.', 'invalid');
    }
    const ok = await confirmAgentAction(`Allow the agent to navigate to ${path}?`);
    if (!ok) return toolError('Human declined navigation.', 'needs_confirmation');
    const result = navigateApp(path);
    if (!result.ok) return toolError(result.error, 'invalid');
    return toolOk({ navigated: true, path: result.path });
  },
} satisfies ToolExecutors;
