import { getClerkQueue } from '../../api/filings';
import { getDemoCourtId, getDemoRole } from '../../components/auth/LoginScreen';
import { READ_ONLY } from '../annotations';
import { toolError, toolOk } from '../output';
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
          status: {
            type: 'string',
            enum: ['all', 'submitted', 'under_review'],
            description: 'Queue filter status',
          },
          search: { type: 'string', maxLength: 200, description: 'Case title, case number, or #filing number' },
          waiting_48h_only: { type: 'boolean', description: 'Only filings received at least 48 hours ago' },
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        if (getDemoRole() !== 'clerk') {
          return toolError('Clerk role required. Use sign_in_demo_role with role clerk.');
        }
        const courtId = getDemoCourtId();
        if (courtId == null) return toolError('Select an assigned court in the review queue first.');
        const status = (input.status as string) || 'all';
        const data = await getClerkQueue(courtId, {
          page: (input.page as number) || 1, status, search: input.search as string | undefined,
          waiting_48h_only: input.waiting_48h_only as boolean | undefined,
        });
        return toolOk({
          court_id: courtId,
          status,
          total: data.total,
          waiting_48h: data.waiting_48h,
          oldest_submitted_at: data.oldest_submitted_at,
          as_of: data.as_of,
          filings: data.filings.map((f) => ({
            id: f.id,
            status: f.status,
            case_title: f.case_title,
            submitted_at: f.submitted_at,
            filer_id: f.filer_id,
          })),
        });
      },
    },
    { signal },
  );
}
