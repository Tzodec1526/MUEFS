import { getCase, searchCases } from '../../api/cases';
import { getFilingChecklists, getFilingRequirements } from '../../api/courts';
import { getClerkQueue, getFilingStatusCounts } from '../../api/filings';
import { getDemoCourtId, getDemoRole } from '../../components/auth/LoginScreen';
import { isClerkRole, isFilerRole, type ToolExecutors } from '../definitions';
import { signInRequired } from '../guidance';
import { sanitizeAgentText, toolError, toolOk } from '../output';

export const workflowTools = {
  async attorney_motion_workflow(input) {
    if (!isFilerRole(getDemoRole())) {
      const { message, action } = signInRequired('filer');
      return toolError(message, 'needs_sign_in', { action });
    }

    // registerTools.ts has checked case_id against the schema: absent or an integer id.
    let caseId = input.case_id as number | undefined;
    if (caseId === undefined) {
      const party = (input.party_name as string | undefined) || undefined;
      const caseNum = (input.case_number as string | undefined) || undefined;
      if (!party && !caseNum) {
        return toolError('Provide party_name, case_number, or case_id for the motion target case.', 'invalid');
      }
      const search = await searchCases({ party_name: party, case_number: caseNum, page: 1 });
      if (!search.cases.length) {
        return toolOk({ found: false, message: 'No public case match.' });
      }
      if (search.total > 1) {
        return toolOk({
          needs_case_selection: true,
          total: search.total,
          candidates: search.cases.map((c: { id: number; title: string; case_number: string; court_id: number }) => ({
            id: c.id, case_number: c.case_number, title: sanitizeAgentText(c.title), court_id: c.court_id,
          })),
          message: 'Ask the filer to choose a case, then call this tool with its case_id.',
        });
      }
      caseId = Number(search.cases[0].id);
    }

    const docket = await getCase(caseId);
    if (!docket.can_file) {
      return toolOk({
        needs_case_access: true,
        case_id: docket.id,
        message: 'Court-reviewed case participation is required. Contact the court to confirm filing access.',
        case_path: `/cases/${docket.id}`,
      });
    }
    const [requirements, checklists, counts] = await Promise.all([
      getFilingRequirements(docket.court_id, docket.case_type_id, 'subsequent'),
      getFilingChecklists(docket.court_id, docket.case_type_id),
      getFilingStatusCounts(),
    ]);

    const params = new URLSearchParams({
      case_id: String(docket.id),
      court_id: String(docket.court_id),
      case_type_id: String(docket.case_type_id),
    });

    return toolOk({
      workflow: 'attorney_motion',
      case: {
        id: docket.id,
        number: docket.case_number,
        title: sanitizeAgentText(docket.title),
      },
      draft_filings_pending: counts.draft || 0,
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

  async clerk_triage_workflow() {
    if (!isClerkRole(getDemoRole())) {
      const { message, action } = signInRequired('clerk');
      return toolError(message, 'needs_sign_in', { action });
    }
    const courtId = getDemoCourtId();
    if (courtId == null) {
      return toolError('Select an assigned court in the review queue first.', 'needs_court_assignment',
        { path: '/clerk/queue' });
    }
    const queue = await getClerkQueue(courtId, { page_size: 5 });

    return toolOk({
      workflow: 'clerk_triage',
      court_id: courtId,
      submitted_count: queue.submitted_count,
      under_review_count: queue.under_review_count,
      waiting_48h: queue.waiting_48h,
      as_of: queue.as_of,
      priority_filings: queue.filings.map((f) => ({
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

  async explain_mcr_for_filing(input) {
    // Integer ids, checked against the schema by registerTools.ts; they form API paths.
    const courtId = input.court_id as number;
    const caseTypeId = input.case_type_id as number;
    const filingType = (input.filing_type as string | undefined) || 'subsequent';
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
} satisfies ToolExecutors;
