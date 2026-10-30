import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { FilingFees } from '../../api/documents';
import type { FilingEnvelope } from '../../api/filings';
import FeeAssessmentForm from './FeeAssessmentForm';

afterEach(cleanup);

const fees = { version: 1, paid_cents: 0, review_reason: null } as FilingFees;
const filing = (filing_type: string) => ({
  id: 2, case_title: 'Doe v. Roe', filing_type, status: 'under_review', filing_description: null, documents: [],
}) as unknown as FilingEnvelope;

it.each([
  ['motion', 'Motion'],
  ['subsequent', 'Existing case'],
  ['initial', 'New case'],
  ['service_only', 'Service only'],
])('names a stored %s filing "%s" for the clerk', (filingType, label) => {
  render(<FeeAssessmentForm fees={fees} filing={filing(filingType)} onSaved={() => {}} />);

  const summary = screen.getByText('Doe v. Roe').closest('p');
  expect(summary?.textContent).toBe(`Doe v. Roe · ${label} · Under review`);
});
