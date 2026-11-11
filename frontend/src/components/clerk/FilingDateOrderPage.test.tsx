import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from '../../api/client';
import { CourtContext } from '../auth/CourtSession';
import FilingDateOrderPage from './FilingDateOrderPage';

vi.mock('../../api/client', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/client')>(), apiClient: { get: vi.fn() },
}));

const get = apiClient.get as unknown as Mock<(url: string) => Promise<{ data: unknown }>>;
const court = { court_id: 3, court_name: 'Third Circuit Court', role: 'clerk' };
const record = {
  filing_id: 2, court_id: 3, status: 'under_review', filing_date: '2026-03-02', filing_date_basis: null,
  version: 1, case_id: null, case_number: null, case_filing_date: null, case_date_version: null, order_block: 'Blocked.',
};

function show() {
  render(<MemoryRouter initialEntries={['/filings/2/filing-date']}>
    <CourtContext.Provider value={{ userId: 1, role: 'clerk', courts: [court], court, loading: false, selectCourt: vi.fn(), refresh: vi.fn() } as never}>
      <Routes><Route path="/filings/:filingId/filing-date" element={<FilingDateOrderPage />} /></Routes>
    </CourtContext.Provider>
  </MemoryRouter>);
}

afterEach(() => {
  cleanup();
  get.mockReset();
});

it('shows the first receipt that sets the filing date and the latest resubmission apart', async () => {
  get.mockResolvedValue({ data: {
    ...record, submission_count: 2, filed_at: '2026-03-02T12:00:00Z', submitted_at: '2026-03-05T15:30:00Z',
  } });
  show();

  expect(await screen.findByText(/^First received: /)).toBeTruthy();
  expect(screen.getByText(/^Latest submission: /)).toBeTruthy();
  expect(screen.queryByText(/^Received: /)).toBeNull();
});

it('shows one receipt time when the filing was submitted once', async () => {
  get.mockResolvedValue({ data: {
    ...record, submission_count: 1, filed_at: '2026-03-02T12:00:00Z', submitted_at: '2026-03-02T12:00:00Z',
  } });
  show();

  expect(await screen.findByText(/^Received: /)).toBeTruthy();
  expect(screen.queryByText(/^First received: /)).toBeNull();
  expect(screen.queryByText(/^Latest submission: /)).toBeNull();
});
