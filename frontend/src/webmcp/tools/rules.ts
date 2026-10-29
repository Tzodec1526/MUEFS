import { getFilingChecklists, getFilingRequirements } from '../../api/courts';
import type { ToolExecutors } from '../definitions';
import { toolOk } from '../output';

/** Court and case type ids arrive checked as integers (registerTools.ts); they form API paths. */
export const rulesTools = {
  async get_filing_requirements(input) {
    const courtId = input.court_id as number;
    const caseTypeId = input.case_type_id as number;
    const reqs = await getFilingRequirements(courtId, caseTypeId, input.filing_type as string | undefined);
    return toolOk({
      court_id: courtId,
      case_type_id: caseTypeId,
      requirements: reqs.map((r) => ({
        code: r.document_type_code,
        required: r.is_required,
        description: r.description,
        mcr: r.mcr_reference,
        page_limit: r.page_limit,
      })),
    });
  },

  async get_motion_checklists(input) {
    const lists = await getFilingChecklists(input.court_id as number, input.case_type_id as number);
    return toolOk({
      checklists: lists.map((c) => ({
        motion_type: c.motion_type,
        items: c.checklist_items?.items || [],
        help_text: c.help_text,
        mcr_url: c.mcr_url,
      })),
    });
  },
} satisfies ToolExecutors;
