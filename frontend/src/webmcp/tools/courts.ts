import { listCourts } from '../../api/courts';
import { READ_ONLY } from '../annotations';
import { sanitizeAgentText, toolError, toolOk } from '../output';
import type { ModelContext } from '../types';

export async function registerCourtTools(mc: ModelContext, signal?: AbortSignal): Promise<void> {
  await mc.registerTool(
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
          page: { type: 'integer', minimum: 1, default: 1 },
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        try {
          const data = await listCourts({
            q: (input.query as string) || undefined,
            page: (input.page as number) || 1,
            page_size: 10,
          });
          return toolOk({
            total: data.total,
            courts: data.courts.map((c) => ({
              id: c.id,
              name: sanitizeAgentText(c.name),
              county: c.county,
              city: c.city,
              court_type: c.court_type,
            })),
          });
        } catch {
          return toolError('Could not load courts.');
        }
      },
    },
    { signal },
  );
}
