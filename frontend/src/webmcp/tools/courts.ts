import { listCourts } from '../../api/courts';
import type { ToolExecutors } from '../definitions';
import { sanitizeAgentText, toolOk } from '../output';

export const courtTools = {
  async list_courts(input) {
    const data = await listCourts({
      q: (input.query as string | undefined) || undefined,
      page: (input.page as number | undefined) ?? 1,
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
  },
} satisfies ToolExecutors;
