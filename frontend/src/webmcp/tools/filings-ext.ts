import { getFiling, listFilings, validateFiling } from '../../api/filings';
import type { ToolExecutors } from '../definitions';
import { sanitizeAgentText, toolOk } from '../output';

/** Record text that may be missing; present text is sanitized like every other record. */
function recordText(value: string | null | undefined): string | null {
  return value ? sanitizeAgentText(value) : null;
}

/**
 * Filer tools; registerTools.ts checks the filer role and the input before each call and turns
 * API failures into error results. Case captions and descriptions can come from other parties.
 */
export const filingTools = {
  async list_my_filings(input) {
    const data = await listFilings({
      status: input.status as string | undefined,
      page: (input.page as number | undefined) ?? 1,
    });
    return toolOk({
      total: data.total,
      filings: data.filings.map((f) => ({
        id: f.id,
        status: f.status,
        case_title: recordText(f.case_title),
        description: recordText(f.filing_description),
        court_id: f.court_id,
        updated_at: f.updated_at,
      })),
    });
  },

  async get_filing_details(input) {
    const f = await getFiling(input.filing_id as number);
    return toolOk({
      filing: {
        id: f.id,
        status: f.status,
        case_title: recordText(f.case_title),
        description: recordText(f.filing_description),
        court_id: f.court_id,
        case_id: f.case_id,
        documents: f.documents.map((d) => ({
          id: d.id,
          type: d.document_type_code,
          title: recordText(d.title),
          pages: d.page_count,
        })),
        fee_waiver_requested: f.fee_waiver_requested,
        // Null until the court decides the request.
        fee_waiver_granted: f.fee_waiver_granted,
        fee_waiver_decided_at: f.fee_waiver_decided_at,
      },
    });
  },

  async validate_filing(input) {
    const v = await validateFiling(input.filing_id as number);
    // Messages quote document titles.
    const clean = (messages: string[]) => messages.map((m) => sanitizeAgentText(m));
    return toolOk({
      is_valid: v.is_valid,
      errors: clean(v.errors),
      warnings: clean(v.warnings),
      missing_required_documents: clean(v.missing_required_documents),
    });
  },
} satisfies ToolExecutors;
