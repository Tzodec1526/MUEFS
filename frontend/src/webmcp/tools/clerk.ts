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
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        if (getDemoRole() !== 'clerk') {
          return toolError('Clerk role required. Use sign_in_demo_role with role clerk.');
        }
        const courtId = getDemoCourtId() || 3;
        const data = await getClerkQueue(courtId, (input.page as number) || 1, 'all');
        return toolOk({
          court_id: courtId,
          total: data.total,
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

  await mc.registerTool(
    {
      name: 'clerk_queue_summary',
      title: 'Clerk queue summary',
      description:
        'High-level counts of pending review work for clerks — use before drilling into the queue UI.',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_ONLY,
      async execute() {
        if (getDemoRole() !== 'clerk') {
          return toolError('Clerk role required.');
        }
        const courtId = getDemoCourtId() || 3;
        const [pending, review] = await Promise.all([
          getClerkQueue(courtId, 1, 'submitted'),
          getClerkQueue(courtId, 1, 'under_review'),
        ]);
        return toolOk({
          court_id: courtId,
          submitted_count: pending.total,
          under_review_count: review.total,
          oldest_submitted: pending.filings[0]?.submitted_at || null,
          hint: 'Use get_clerk_review_queue for the full list or navigate_to /clerk/queue',
        });
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'open_filing_for_review',
      title: 'Open filing for review',
      description:
        'Build a deep link into the clerk queue focused on one filing id. Does not accept or reject — human clerk decides.',
      inputSchema: {
        type: 'object',
        required: ['filing_id'],
        properties: {
          filing_id: { type: 'integer', description: 'Filing envelope id from the queue' },
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        if (getDemoRole() !== 'clerk') {
          return toolError('Clerk role required.');
        }
        const filingId = Number(input.filing_id);
        if (!Number.isFinite(filingId) || filingId <= 0) {
          return toolError('Provide a positive filing_id.');
        }
        const path = `/clerk/queue?filing_id=${filingId}`;
        return toolOk({
          filing_id: filingId,
          review_path: path,
          navigate_hint: 'Call navigate_to with review_path after the clerk confirms.',
        });
      },
    },
    { signal },
  );
}
