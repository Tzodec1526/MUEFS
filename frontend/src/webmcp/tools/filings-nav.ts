import { READ_ONLY } from '../annotations';
import { toolOk } from '../output';
import type { ModelContext } from '../types';

export async function registerFilingNavTools(mc: ModelContext, signal?: AbortSignal): Promise<void> {
  await mc.registerTool(
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
          case_id: { type: 'integer' },
          court_id: { type: 'integer' },
          case_type_id: { type: 'integer' },
          case_title: { type: 'string' },
          service_only: { type: 'boolean', default: false },
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        const params = new URLSearchParams({
          case_id: String(input.case_id),
          court_id: String(input.court_id),
          case_type_id: String(input.case_type_id),
        });
        if (input.case_title) {
          params.set('case_title', String(input.case_title));
        }
        if (input.service_only) {
          params.set('service_only', 'true');
        }
        return toolOk({
          path: `/filing/new?${params}`,
          hint: 'Open this path in MUEFS or call navigate_to with this path.',
        });
      },
    },
    { signal },
  );
}
