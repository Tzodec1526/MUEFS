import { getFiling, listFilings, validateFiling } from '../../api/filings';
import { getDemoRole } from '../../components/auth/LoginScreen';
import { READ_ONLY } from '../annotations';
import { toolError, toolOk } from '../output';
import type { ModelContext } from '../types';

export async function registerExtendedFilingTools(
  mc: ModelContext,
  signal?: AbortSignal,
): Promise<void> {
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
      annotations: READ_ONLY,
      async execute(input) {
        const role = getDemoRole();
        if (!role || role === 'public' || role === 'clerk') {
          return toolError('Sign in as attorney or self-represented litigant to list filings.');
        }
        const data = await listFilings({
          status: input.status as string | undefined,
          page: (input.page as number) || 1,
        });
        return toolOk({
          total: data.total,
          filings: data.filings.map((f) => ({
            id: f.id,
            status: f.status,
            case_title: f.case_title,
            description: f.filing_description,
            court_id: f.court_id,
            updated_at: f.updated_at,
          })),
        });
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'get_filing_details',
      title: 'Filing details',
      description: 'Return status, documents, and fee waiver state for one of your filings.',
      inputSchema: {
        type: 'object',
        required: ['filing_id'],
        properties: {
          filing_id: { type: 'integer' },
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        const role = getDemoRole();
        if (!role || role === 'public' || role === 'clerk') {
          return toolError('Sign in as attorney or self-represented litigant.');
        }
        try {
          const f = await getFiling(Number(input.filing_id));
          return toolOk({
            filing: {
              id: f.id,
              status: f.status,
              case_title: f.case_title,
              description: f.filing_description,
              court_id: f.court_id,
              case_id: f.case_id,
              documents: f.documents.map((d) => ({
                id: d.id,
                type: d.document_type_code,
                title: d.title,
                pages: d.page_count,
              })),
              fee_waiver_requested: f.fee_waiver_requested,
            },
          });
        } catch {
          return toolError('Filing not found or not accessible.');
        }
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'validate_filing',
      title: 'Validate filing before submit',
      description:
        'Run MCR companion and required-document checks on a draft filing. ' +
        'Returns errors, warnings, and missing required documents.',
      inputSchema: {
        type: 'object',
        required: ['filing_id'],
        properties: {
          filing_id: { type: 'integer' },
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        const role = getDemoRole();
        if (!role || role === 'public' || role === 'clerk') {
          return toolError('Sign in as attorney or self-represented litigant.');
        }
        try {
          const v = await validateFiling(Number(input.filing_id));
          return toolOk({
            is_valid: v.is_valid,
            errors: v.errors,
            warnings: v.warnings,
            missing_required_documents: v.missing_required_documents,
          });
        } catch {
          return toolError('Could not validate filing.');
        }
      },
    },
    { signal },
  );
}
