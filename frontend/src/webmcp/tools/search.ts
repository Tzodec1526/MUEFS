import { getCase, searchCases } from '../../api/cases';
import { UNTRUSTED_RECORDS } from '../annotations';
import { sanitizeAgentText, toolOk } from '../output';
import type { ModelContext } from '../types';

export async function registerSearchTools(mc: ModelContext, signal?: AbortSignal): Promise<void> {
  await mc.registerTool(
    {
      name: 'search_cases',
      title: 'Search Michigan public court records',
      description:
        'Search the statewide public docket by party name and/or case number. ' +
        'Sealed matters are excluded. Returns case id, number, title, status, and parties.',
      inputSchema: {
        type: 'object',
        properties: {
          party_name: { type: 'string', description: 'Party or litigant name (partial match)' },
          case_number: { type: 'string', description: 'Case number (partial match)' },
          page: { type: 'integer', minimum: 1, default: 1 },
        },
      },
      annotations: UNTRUSTED_RECORDS,
      async execute(input) {
        const data = await searchCases({
          party_name: (input.party_name as string) || undefined,
          case_number: (input.case_number as string) || undefined,
          page: (input.page as number) || 1,
        });
        return toolOk({
          total: data.total,
          page: data.page,
          cases: data.cases.map(
            (c: {
              id: number;
              case_number: string;
              title: string;
              status: string;
              filed_date: string;
              court_id: number;
              case_type_id: number;
              participants?: Array<{ party_name: string; role: string }>;
            }) => ({
              id: c.id,
              case_number: c.case_number,
              title: sanitizeAgentText(c.title),
              status: c.status,
              filed_date: c.filed_date,
              court_id: c.court_id,
              case_type_id: c.case_type_id,
              parties: (c.participants || []).map(
                (p) => `${sanitizeAgentText(p.party_name)} (${p.role})`,
              ),
            }),
          ),
        });
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'get_case_docket',
      title: 'Open a case docket',
      description:
        'Return public docket details for a case by numeric id (from search_cases). ' +
        'Sealed cases require an authorized account and will return forbidden.',
      inputSchema: {
        type: 'object',
        required: ['case_id'],
        properties: {
          case_id: { type: 'integer', description: 'Internal case id from search results' },
        },
      },
      annotations: UNTRUSTED_RECORDS,
      async execute(input) {
        const caseId = input.case_id as number;
        const data = await getCase(caseId);
        return toolOk({
          id: data.id,
          case_number: data.case_number,
          title: sanitizeAgentText(data.title),
          status: data.status,
          is_sealed: data.is_sealed,
          filed_date: data.filed_date,
          court_id: data.court_id,
          case_type_id: data.case_type_id,
          participants: (data.participants || []).map(
            (p: { party_name: string; role: string; attorney_bar_number?: string | null }) => ({
              party_name: sanitizeAgentText(p.party_name),
              role: p.role,
              attorney_bar_number: p.attorney_bar_number,
            }),
          ),
        });
      },
    },
    { signal },
  );
}
