import { listFilings } from '../../api/filings';
import { getDemoRole } from '../../components/auth/LoginScreen';
import type { ModelContext } from '../types';

export async function registerFilingTools(mc: ModelContext, signal?: AbortSignal): Promise<void> {
  await mc.registerTool(
    {
      name: 'list_my_filings',
      title: 'List my e-filings',
      description:
        'List filings for the current signed-in filer (attorney or self-represented). ' +
        'Optional status filter: draft, submitted, under_review, accepted, rejected, returned.',
      inputSchema: {
        type: 'object',
        properties: {
          status: {
            type: 'string',
            enum: ['draft', 'submitted', 'under_review', 'accepted', 'rejected', 'returned', 'served'],
          },
          page: { type: 'integer', minimum: 1, default: 1 },
        },
      },
      async execute(input) {
        const role = getDemoRole();
        if (!role || role === 'public' || role === 'clerk') {
          return JSON.stringify({
            error: 'Sign in as attorney or self-represented litigant to list filings.',
          });
        }
        const data = await listFilings({
          status: input.status as string | undefined,
          page: (input.page as number) || 1,
        });
        return JSON.stringify({
          total: data.total,
          filings: data.filings.map(
            (f: {
              id: number;
              status: string;
              case_title: string | null;
              filing_description: string | null;
              court_id: number;
              updated_at: string;
            }) => ({
              id: f.id,
              status: f.status,
              case_title: f.case_title,
              description: f.filing_description,
              court_id: f.court_id,
              updated_at: f.updated_at,
            }),
          ),
        });
      },
    },
    { signal },
  );
}
