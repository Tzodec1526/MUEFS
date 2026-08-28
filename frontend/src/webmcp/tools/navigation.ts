import { MUTATING } from '../annotations';
import { confirmAgentAction, wantsConfirmation } from '../confirm';
import { navigateApp } from '../navigate';
import { toolError, toolOk } from '../output';
import type { ModelContext } from '../types';

export async function registerNavigationTools(
  mc: ModelContext,
  signal?: AbortSignal,
): Promise<void> {
  await mc.registerTool(
    {
      name: 'navigate_to',
      title: 'Navigate within MUEFS',
      description:
        'Open an in-app path on the same origin. Examples: /cases/search?party=Smith, ' +
        '/filing/new?case_id=1&court_id=3&case_type_id=5, /clerk/queue. ' +
        'Mutating: ask the human, or pass confirmed=true after they agree. ' +
        'Does not leave the Michigan e-filing portal.',
      inputSchema: {
        type: 'object',
        required: ['path'],
        properties: {
          path: {
            type: 'string',
            description: 'App-relative path starting with /',
          },
          confirmed: {
            type: 'boolean',
            description: 'Set true after the human confirms navigation',
          },
        },
      },
      annotations: MUTATING,
      async execute(input) {
        const path = String(input.path || '');
        if (wantsConfirmation(input)) {
          const ok = await confirmAgentAction(`Allow the agent to navigate to ${path}?`);
          if (!ok) return toolError('Human declined navigation.', 'needs_confirmation');
        }
        const result = navigateApp(path);
        if (!result.ok) return toolError(result.error);
        return toolOk({ navigated: true, path: result.path });
      },
    },
    { signal },
  );
}
