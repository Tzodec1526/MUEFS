import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from '../../api/client';
import { CourtContext } from '../auth/CourtSession';
import FeeReviewQueue from '../clerk/FeeReviewQueue';
import FilingDateOrderPage from '../clerk/FilingDateOrderPage';
import { ToastProvider } from './Toast';

vi.mock('../../api/client', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/client')>(), apiClient: { get: vi.fn() },
}));

const get = apiClient.get as unknown as Mock<(url: string) => Promise<{ data: unknown }>>;
const court = { court_id: 3, court_name: 'Third Circuit Court', role: 'clerk' };

function show(url: string, path: string, page: ReactNode) {
  render(<MemoryRouter initialEntries={[url]}>
    <ToastProvider>
      <CourtContext.Provider value={{ userId: 1, role: 'clerk', courts: [court], court, loading: false, selectCourt: vi.fn(), refresh: vi.fn() } as never}>
        <Routes><Route path={path} element={page} /></Routes>
      </CourtContext.Provider>
    </ToastProvider>
  </MemoryRouter>);
}

afterEach(() => {
  cleanup();
  get.mockReset();
});

it('names a filing status in words in the fee review queue', async () => {
  get.mockResolvedValue({ data: {
    total: 1, page: 1, filings: [{ id: 2, case_title: 'Doe v. Roe', filer_name: 'Pat Lee', status: 'under_review', requested_at: '2026-03-02T12:00:00Z' }],
  } });
  show('/clerk/fee-reviews', '/clerk/fee-reviews', <FeeReviewQueue />);

  expect((await screen.findByText(/Pat Lee/)).textContent).toMatch(/^Pat Lee · Under review · Requested /);
});

it('names a filing status in words on the filing date page', async () => {
  get.mockResolvedValue({ data: {
    filing_id: 2, court_id: 3, status: 'under_review', submission_count: 1, submitted_at: '2026-03-02T12:00:00Z', filing_date: null,
    filing_date_basis: null, version: 1, case_id: null, case_number: null, case_filing_date: null, case_date_version: null, order_block: 'Blocked.',
  } });
  show('/filings/2/filing-date', '/filings/:filingId/filing-date', <FilingDateOrderPage />);

  expect(await screen.findByText('Submission 1 · Under review')).toBeTruthy();
});
