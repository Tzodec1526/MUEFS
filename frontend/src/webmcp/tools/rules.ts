import { getFilingChecklists, getFilingRequirements } from '../../api/courts';
import { READ_ONLY } from '../annotations';
import { toolError, toolOk } from '../output';
import type { ModelContext } from '../types';

export async function registerRulesTools(mc: ModelContext, signal?: AbortSignal): Promise<void> {
  await mc.registerTool(
    {
      name: 'get_filing_requirements',
      title: 'Filing document requirements',
      description:
        'Return MCR-referenced required and optional documents for a court and case type. ' +
        'Use before uploading in the filing wizard.',
      inputSchema: {
        type: 'object',
        required: ['court_id', 'case_type_id'],
        properties: {
          court_id: { type: 'integer' },
          case_type_id: { type: 'integer' },
          filing_type: {
            type: 'string',
            enum: ['initial', 'subsequent', 'motion', 'service_only'],
            description: 'Scope requirements to new case vs motion',
          },
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        try {
          const reqs = await getFilingRequirements(
            Number(input.court_id),
            Number(input.case_type_id),
            input.filing_type as string | undefined,
          );
          return toolOk({
            court_id: input.court_id,
            case_type_id: input.case_type_id,
            requirements: reqs.map((r) => ({
              code: r.document_type_code,
              required: r.is_required,
              description: r.description,
              mcr: r.mcr_reference,
              page_limit: r.page_limit,
            })),
          });
        } catch {
          return toolError('Could not load filing requirements.');
        }
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'get_motion_checklists',
      title: 'Motion companion checklists',
      description:
        'MCR 2.119 motion companions (brief, proposed order, proof of service) for a court/case type. ' +
        'Use when advising a filer what to attach to a motion.',
      inputSchema: {
        type: 'object',
        required: ['court_id', 'case_type_id'],
        properties: {
          court_id: { type: 'integer' },
          case_type_id: { type: 'integer' },
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        try {
          const lists = await getFilingChecklists(
            Number(input.court_id),
            Number(input.case_type_id),
          );
          return toolOk({
            checklists: lists.map((c) => ({
              motion_type: c.motion_type,
              items: c.checklist_items?.items || [],
              help_text: c.help_text,
              mcr_url: c.mcr_url,
            })),
          });
        } catch {
          return toolError('Could not load motion checklists.');
        }
      },
    },
    { signal },
  );
}
