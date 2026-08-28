import { getCase, searchCases } from '../../api/cases';
import { getFilingChecklists, getFilingRequirements } from '../../api/courts';
import { getClerkQueue, listFilings } from '../../api/filings';
import { getDemoCourtId, getDemoRole } from '../../components/auth/LoginScreen';
import { UNTRUSTED_RECORDS, READ_ONLY } from '../annotations';
import { sanitizeAgentText, toolError, toolOk } from '../output';
import type { ModelContext } from '../types';

export async function registerWorkflowTools(mc: ModelContext, signal?: AbortSignal): Promise<void> {
  await mc.registerTool(
    {
      name: 'attorney_motion_workflow',
      title: 'Attorney motion workflow (full plan)',
      description:
        'Challenge showcase workflow: verify filer role, search docket, load MCR requirements ' +
        'and motion checklists, list draft filings, return wizard URL and plain-language plan. ' +
        'Does not submit — human completes wizard.',
      inputSchema: {
        type: 'object',
        properties: {
          party_name: { type: 'string' },
          case_number: { type: 'string' },
        },
      },
      annotations: UNTRUSTED_RECORDS,
      async execute(input) {
        const role = getDemoRole();
        if (role !== 'attorney' && role !== 'srl') {
          return toolOk({
            needs_sign_in: true,
            message: 'Sign in as attorney or srl first.',
            action: { tool: 'sign_in_demo_role', role: 'attorney' },
          });
        }

        const party = (input.party_name as string) || undefined;
        const caseNum = (input.case_number as string) || undefined;
        if (!party && !caseNum) {
          return toolError('Provide party_name or case_number for the motion target case.');
        }

        const search = await searchCases({ party_name: party, case_number: caseNum, page: 1 });
        if (!search.cases?.length) {
          return toolOk({ found: false, message: 'No public case match.' });
        }

        const hit = search.cases[0];
        const docket = await getCase(hit.id);
        const [requirements, checklists, drafts] = await Promise.all([
          getFilingRequirements(docket.court_id, docket.case_type_id, 'subsequent'),
          getFilingChecklists(docket.court_id, docket.case_type_id),
          listFilings({ status: 'draft', page: 1 }),
        ]);

        const params = new URLSearchParams({
          case_id: String(docket.id),
          court_id: String(docket.court_id),
          case_type_id: String(docket.case_type_id),
          case_title: docket.title,
        });

        return toolOk({
          workflow: 'attorney_motion',
          case: {
            id: docket.id,
            number: docket.case_number,
            title: sanitizeAgentText(docket.title),
          },
          draft_filings_pending: drafts.total,
          required_documents: requirements
            .filter((r) => r.is_required)
            .map((r) => ({ code: r.document_type_code, label: r.description, mcr: r.mcr_reference })),
          motion_types: checklists.map((c) => c.motion_type),
          plan: [
            `Review ${sanitizeAgentText(docket.title)} (${docket.case_number}).`,
            'Gather motion, brief in support, proposed order, and proof of service per MCR 2.119.',
            'Open the pre-filled wizard — upload PDFs — human submits.',
          ],
          filing_wizard_path: `/filing/new?${params}`,
          navigate_hint: 'Call navigate_to with filing_wizard_path after user confirms.',
        });
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'clerk_triage_workflow',
      title: 'Clerk triage workflow',
      description:
        'Challenge showcase for court staff: queue counts, oldest pending filings, ' +
        'and navigation to the review UI. Requires clerk role.',
      inputSchema: { type: 'object', properties: {} },
      annotations: READ_ONLY,
      async execute() {
        if (getDemoRole() !== 'clerk') {
          return toolOk({
            needs_sign_in: true,
            action: { tool: 'sign_in_demo_role', role: 'clerk' },
          });
        }
        const courtId = getDemoCourtId() || 3;
        const [submitted, review] = await Promise.all([
          getClerkQueue(courtId, 1, 'submitted'),
          getClerkQueue(courtId, 1, 'under_review'),
        ]);
        const combined = [...submitted.filings, ...review.filings].slice(0, 5);

        return toolOk({
          workflow: 'clerk_triage',
          court_id: courtId,
          submitted_count: submitted.total,
          under_review_count: review.total,
          priority_filings: combined.map((f) => ({
            id: f.id,
            title: f.case_title ? sanitizeAgentText(f.case_title) : null,
            status: f.status,
            submitted_at: f.submitted_at,
          })),
          plan: [
            'Review oldest submitted filings first.',
            'Open /clerk/queue for batch accept and quick reject reasons.',
            'Agent may summarize — clerk decides accept/return.',
          ],
          queue_path: '/clerk/queue',
        });
      },
    },
    { signal },
  );

  await mc.registerTool(
    {
      name: 'explain_mcr_for_filing',
      title: 'Explain MCR filing rules',
      description:
        'Plain-language summary of required documents and motion companions for a court/case type. ' +
        'Ideal for self-represented litigants working with an agent.',
      inputSchema: {
        type: 'object',
        required: ['court_id', 'case_type_id'],
        properties: {
          court_id: { type: 'integer' },
          case_type_id: { type: 'integer' },
          filing_type: {
            type: 'string',
            enum: ['initial', 'subsequent', 'motion'],
          },
        },
      },
      annotations: READ_ONLY,
      async execute(input) {
        const courtId = Number(input.court_id);
        const caseTypeId = Number(input.case_type_id);
        const filingType = (input.filing_type as string) || 'subsequent';
        const [requirements, checklists] = await Promise.all([
          getFilingRequirements(courtId, caseTypeId, filingType),
          getFilingChecklists(courtId, caseTypeId),
        ]);

        const required = requirements.filter((r) => r.is_required);
        const optional = requirements.filter((r) => !r.is_required);

        return toolOk({
          summary: `This filing needs ${required.length} required document type(s) and ${optional.length} optional type(s).`,
          required: required.map((r) => ({
            what: r.description,
            rule: r.mcr_reference,
          })),
          optional: optional.slice(0, 8).map((r) => r.description),
          motion_guides: checklists.map((c) => ({
            type: c.motion_type,
            must_include: (c.checklist_items?.items || [])
              .filter((i) => i.required)
              .map((i) => i.label),
            tip: c.help_text,
          })),
          disclaimer: 'Demo guidance only — court grants and local rules control.',
        });
      },
    },
    { signal },
  );
}
