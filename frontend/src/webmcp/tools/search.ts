import { getCase, searchCases } from '../../api/cases';
import type { ToolExecutors } from '../definitions';
import { sanitizeAgentText, toolOk } from '../output';
import { caseDates, caseSearchResult } from '../records';

/** Input arrives checked against each tool's schema (registerTools.ts); ids are integers. */
export const searchTools = {
  async search_cases(input) {
    const data = await searchCases({
      party_name: (input.party_name as string | undefined) || undefined,
      case_number: (input.case_number as string | undefined) || undefined,
      court_id: input.court_id as number | undefined,
      page: (input.page as number | undefined) ?? 1,
    });
    return caseSearchResult(data);
  },

  async get_case_docket(input) {
    const data = await getCase(input.case_id as number);
    return toolOk({
      id: data.id,
      case_number: data.case_number,
      title: sanitizeAgentText(data.title),
      status: data.status,
      is_sealed: data.is_sealed,
      ...caseDates(data),
      court_id: data.court_id,
      case_type_id: data.case_type_id,
      participants: (data.participants || []).map((p) => ({
        party_name: sanitizeAgentText(p.party_name),
        role: p.role,
        attorney_bar_number: p.attorney_bar_number ? sanitizeAgentText(p.attorney_bar_number) : null,
      })),
    });
  },
} satisfies ToolExecutors;
