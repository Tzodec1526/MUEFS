import { getClerkQueue } from '../../api/filings';
import { getDemoCourtId, getDemoRole } from '../../components/auth/LoginScreen';
import type { ModelContext } from '../types';

export async function registerClerkTools(mc: ModelContext, signal?: AbortSignal): Promise<void> {
  await mc.registerTool(
    {
      name: 'get_clerk_review_queue',
      title: 'Clerk review queue',
      description:
        'List filings pending clerk review for the current court. Requires clerk role. ' +
        'Returns envelope id, status, case title, and submitted date.',
      inputSchema: {
        type: 'object',
        properties: {
          page: { type: 'integer', minimum: 1, default: 1 },
        },
      },
      async execute(input) {
        if (getDemoRole() !== 'clerk') {
          return JSON.stringify({ error: 'Clerk role required. Switch role on the login screen.' });
        }
        const courtId = getDemoCourtId() || 3;
        const data = await getClerkQueue(courtId, (input.page as number) || 1, 'all');
        return JSON.stringify({
          court_id: courtId,
          total: data.total,
          filings: data.filings.map(
            (f: {
              id: number;
              status: string;
              case_title: string | null;
              submitted_at: string | null;
              filer_id: number;
            }) => ({
              id: f.id,
              status: f.status,
              case_title: f.case_title,
              submitted_at: f.submitted_at,
              filer_id: f.filer_id,
            }),
          ),
        });
      },
    },
    { signal },
  );
}
