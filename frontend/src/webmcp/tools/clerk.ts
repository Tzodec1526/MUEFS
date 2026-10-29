import { getClerkQueue } from '../../api/filings';
import { getDemoCourtId } from '../../components/auth/LoginScreen';
import type { ToolExecutors } from '../definitions';
import { toolError } from '../output';
import { clerkQueueResult } from '../records';

/** Clerk tools; registerTools.ts checks the clerk role and the input before each call. */
export const clerkTools = {
  async get_clerk_review_queue(input) {
    const courtId = getDemoCourtId();
    if (courtId == null) {
      return toolError('Select an assigned court in the review queue first.', 'needs_court_assignment',
        { path: '/clerk/queue' });
    }
    const status = (input.status as string | undefined) || 'all';
    const data = await getClerkQueue(courtId, {
      page: (input.page as number | undefined) ?? 1,
      status,
      search: (input.search as string | undefined) || undefined,
      waiting_48h_only: input.waiting_48h_only as boolean | undefined,
    });
    return clerkQueueResult(courtId, status, data);
  },
} satisfies ToolExecutors;
