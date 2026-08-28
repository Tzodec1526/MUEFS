import { getCase, searchCases } from '../../api/cases';
import { getFilingChecklists } from '../../api/courts';
import { UNTRUSTED_RECORDS } from '../annotations';
import { sanitizeAgentText, toolError, toolOk } from '../output';
import type { ModelContext } from '../types';

export async function registerOrchestrationTools(
  mc: ModelContext,
  signal?: AbortSignal,
): Promise<void> {
  await mc.registerTool(
    {
      name: 'research_case_for_motion',
      title: 'Research case and plan a motion filing',
      description:
        'End-to-end agent workflow for Michigan e-filing: search the public docket, open a case, ' +
        'load MCR motion checklists, and return a pre-filled filing wizard URL. ' +
        'Ideal for “find Smith v Jones and help me file a motion” prompts. ' +
        'Does not submit filings — human completes the wizard.',
      inputSchema: {
        type: 'object',
        properties: {
          party_name: { type: 'string', description: 'Party name to search' },
          case_number: { type: 'string', description: 'Case number to search' },
          case_id: {
            type: 'integer',
            description: 'Skip search when case id is already known',
          },
        },
      },
      annotations: UNTRUSTED_RECORDS,
      async execute(input) {
        try {
          let caseId = input.case_id ? Number(input.case_id) : null;
          let searchHit: {
            id: number;
            case_number: string;
            title: string;
            court_id: number;
            case_type_id: number;
          } | null = null;

          if (!caseId) {
            const party = (input.party_name as string) || undefined;
            const caseNum = (input.case_number as string) || undefined;
            if (!party && !caseNum) {
              return toolError('Provide party_name, case_number, or case_id.');
            }
            const data = await searchCases({
              party_name: party,
              case_number: caseNum,
              page: 1,
            });
            if (!data.cases?.length) {
              return toolOk({
                found: false,
                message: 'No matching public cases. Try a different party or case number.',
              });
            }
            const c = data.cases[0];
            searchHit = {
              id: c.id,
              case_number: c.case_number,
              title: c.title,
              court_id: c.court_id,
              case_type_id: c.case_type_id,
            };
            caseId = c.id;
          }

          const docket = await getCase(caseId!);
          if (docket.is_sealed) {
            return toolError('Case is sealed. Sign in as an authorized party or counsel.');
          }

          const courtId = docket.court_id;
          const caseTypeId = docket.case_type_id;
          const checklists = await getFilingChecklists(courtId, caseTypeId);

          const params = new URLSearchParams({
            case_id: String(docket.id),
            court_id: String(courtId),
            case_type_id: String(caseTypeId),
            case_title: docket.title,
          });

          return toolOk({
            found: true,
            search_hit: searchHit,
            case: {
              id: docket.id,
              case_number: docket.case_number,
              title: sanitizeAgentText(docket.title),
              status: docket.status,
              court_id: courtId,
              case_type_id: caseTypeId,
              parties: (docket.participants || []).map(
                (p: { party_name: string; role: string }) =>
                  `${sanitizeAgentText(p.party_name)} (${p.role})`,
              ),
            },
            motion_checklists: checklists.map((c) => ({
              motion_type: c.motion_type,
              required_items: (c.checklist_items?.items || [])
                .filter((i) => i.required)
                .map((i) => i.label),
              help_text: c.help_text,
            })),
            next_steps: [
              'Sign in as attorney or self-represented litigant if not already.',
              'Open the pre-filled filing wizard URL.',
              'Upload motion papers per MCR 2.119 companions.',
              'Human filer reviews and submits — agent does not submit alone.',
            ],
            filing_wizard_path: `/filing/new?${params}`,
            case_detail_path: `/cases/${docket.id}`,
          });
        } catch {
          return toolError('Research workflow failed. Try search_cases then get_case_docket.');
        }
      },
    },
    { signal },
  );
}
