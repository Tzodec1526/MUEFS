/** How case records read to agents, from the imperative tools and the declarative forms alike. */

import type { CaseSearchResult } from '../api/cases';
import type { ClerkQueue } from '../api/filings';
import { sanitizeAgentText, toolOk } from './output';

/**
 * A case's date as the UI shows it: the court's filing date or, until the court calendar sets
 * one, the stored timestamp, which is not calendar-verified and is not the filing date.
 */
export function caseDates(c: { filing_date: string | null; filed_date: string }) {
  return c.filing_date
    ? { filing_date: c.filing_date }
    : { filing_date: null, stored_date_not_calendar_verified: c.filed_date };
}

/** The search_cases result; also the response to an agent's search_cases_form submission. */
export function caseSearchResult(data: { cases: CaseSearchResult[]; total: number; page: number }): string {
  return toolOk({
    total: data.total,
    page: data.page,
    cases: data.cases.map((c) => ({
      id: c.id,
      case_number: c.case_number,
      title: sanitizeAgentText(c.title),
      status: c.status,
      ...caseDates(c),
      court_id: c.court_id,
      court_name: sanitizeAgentText(c.court_name),
      court_county: sanitizeAgentText(c.court_county),
      case_type_id: c.case_type_id,
      parties: c.participants.map(
        (p) => `${sanitizeAgentText(p.party_name)} (${p.role})`,
      ),
    })),
  });
}

/** The get_clerk_review_queue result; also the response to an agent's review_queue_form submission. */
export function clerkQueueResult(courtId: number, status: string, data: ClerkQueue): string {
  return toolOk({
    court_id: courtId,
    status,
    total: data.total,
    waiting_48h: data.waiting_48h,
    oldest_submitted_at: data.oldest_submitted_at,
    as_of: data.as_of,
    filings: data.filings.map((f) => ({
      id: f.id,
      status: f.status,
      case_title: f.case_title ? sanitizeAgentText(f.case_title) : null,
      submitted_at: f.submitted_at,
      filer_id: f.filer_id,
    })),
  });
}
