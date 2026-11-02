import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { getFiling, validateFiling, type FilingEnvelope } from '../../api/filings';
import FilingReview from './FilingReview';

vi.mock('../../api/filings', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/filings')>(), getFiling: vi.fn(), validateFiling: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const filing = (status: string) => ({
  id: 7, status, filing_type: 'initial', case_title: 'Doe v. Roe', documents: [], fee_waiver_requested: false,
}) as unknown as FilingEnvelope;

const review = (overrides = {}) => render(<MemoryRouter>
  <FilingReview filingId={7} courtName="Third Circuit Court" caseTypeName="General Civil" {...overrides} />
</MemoryRouter>);

it.each([
  ['served', 'Service documents recorded'],
  ['submitted', 'Submitted'],
  ['under_review', 'Under review'],
])('words the %s badge on the confirmation "%s"', (status, label) => {
  review({ submission: filing(status) });

  expect(screen.getByText('Status').parentElement?.textContent).toBe(`Status${label}`);
});

it.each([
  ['served', 'This filing is now recorded for service. View its receipt and current status.'],
  ['under_review', 'This filing is now under review. View its receipt and current status.'],
  ['accepted', 'This filing is now accepted. View its receipt and current status.'],
])('keeps the %s warning a readable sentence', async (status, sentence) => {
  vi.mocked(getFiling).mockResolvedValue(filing(status));
  vi.mocked(validateFiling).mockResolvedValue({ is_valid: true, errors: [], warnings: [], missing_required_documents: [] });
  review();

  const link = await screen.findByRole('link', { name: 'View its receipt and current status' });

  expect(link.closest('p')?.textContent).toBe(sentence);
});
