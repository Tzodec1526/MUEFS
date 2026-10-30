import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from '../../api/client';
import type { CaseDocket } from '../../api/cases';
import { getCaseTypes, type CaseType } from '../../api/courts';
import { addFavorite, listFavorites } from '../../api/favorites';
import { CourtContext } from '../auth/CourtSession';
import { ToastProvider } from '../common/Toast';
import CaseDetailPage from './CaseDetailPage';

vi.mock('../../api/client', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/client')>(), apiClient: { get: vi.fn() },
}));
vi.mock('../../api/courts', () => ({ getCaseTypes: vi.fn() }));
vi.mock('../../api/favorites', () => ({ listFavorites: vi.fn(), addFavorite: vi.fn(), removeFavorite: vi.fn() }));

const PARTICIPATION_NOTICE = /Court-reviewed case participation is required to file documents in this case/;
const get = apiClient.get as unknown as Mock<(url: string) => Promise<{ data: unknown }>>;

function docket(canFile: boolean): CaseDocket {
  return {
    id: 42, court_id: 3, case_number: '2026-000042-CZ', case_type_id: 11, title: 'Smith v. Jones',
    can_manage_records: false, can_file: canFile, status: 'open', filed_date: '2026-03-02',
    filing_date: '2026-03-02', judge_id: null, participants: [], created_at: '2026-03-02T12:00:00Z',
  };
}

const civil: CaseType = {
  id: 11, court_id: 3, code: 'CZ', name: 'General Civil', category: 'civil', filing_fee_cents: 17500,
  description: null, is_active: true,
};

function showCase(caseRecord: CaseDocket, caseTypes: CaseType[] = [civil]) {
  get.mockImplementation(async (url) => {
    const responses: Record<string, unknown> = {
      '/cases/42': caseRecord, '/cases/42/filings': [], '/courts/3': { id: 3, name: 'Third Circuit Court' },
    };
    if (!(url in responses)) throw new Error(`Unexpected request: ${url}`);
    return { data: responses[url] };
  });
  // Like the API: types closed to new cases are listed only when a caller asks for them.
  vi.mocked(getCaseTypes).mockImplementation(async (_court, includeInactive = false) =>
    caseTypes.filter(type => includeInactive || type.is_active));
  vi.mocked(listFavorites).mockResolvedValue({ favorites: [], total: 0 });
  render(
    <MemoryRouter initialEntries={['/cases/42']}>
      <ToastProvider>
        <CourtContext.Provider value={{ role: localStorage.getItem('demo_role'), courts: [], court: undefined, loading: false, selectCourt: () => {}, refresh: () => {} }}>
          <Routes><Route path="/cases/:caseId" element={<CaseDetailPage />} /></Routes>
        </CourtContext.Provider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

function filingLinks(): string[] {
  return screen.queryAllByRole('link').map(link => link.getAttribute('href') ?? '')
    .filter(href => href.startsWith('/filing/new'));
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  localStorage.clear();
});

describe.each(['attorney', 'srl'])('for the %s filer role', (role) => {
  it('explains that court-reviewed participation is needed and offers no filing links', async () => {
    localStorage.setItem('demo_role', role);
    showCase(docket(false));

    expect(await screen.findByText(PARTICIPATION_NOTICE)).toBeTruthy();
    expect(filingLinks()).toEqual([]);
  });

  it('links to new filings by case, court and case type only, never by caption', async () => {
    localStorage.setItem('demo_role', role);
    showCase(docket(true));

    await screen.findByRole('link', { name: 'File with Court' });
    const base = '/filing/new?case_id=42&court_id=3&case_type_id=11';
    expect(filingLinks()).toEqual([base, `${base}&service_only=true`, base]);
    for (const href of filingLinks()) {
      expect(new URL(href, 'http://localhost').searchParams.has('case_title')).toBe(false);
    }
    expect(screen.queryByText(PARTICIPATION_NOTICE)).toBeNull();
  });
});

it('names the case type even after the court closed that type to new cases', async () => {
  showCase(docket(false), [{ ...civil, is_active: false }]);

  expect(await screen.findByText('General Civil')).toBeTruthy();
  expect(screen.queryByText('--')).toBeNull();
});

it('explains a failed favorite update itself when the server sent no detail', async () => {
  localStorage.setItem('demo_role', 'attorney');
  vi.mocked(addFavorite).mockRejectedValue(new Error('Network Error'));
  showCase(docket(true));

  fireEvent.click(await screen.findByRole('button', { name: '☆ Favorite' }));

  expect(await screen.findByText('Could not update favorite')).toBeTruthy();
  expect(screen.getByRole('button', { name: '☆ Favorite' })).toBeTruthy();
});

it("shows the server's explanation of a failed favorite update once, in place of its own", async () => {
  localStorage.setItem('demo_role', 'attorney');
  vi.mocked(addFavorite).mockRejectedValue({ response: { status: 409, data: { detail: 'Case already in favorites' } } });
  showCase(docket(true));

  fireEvent.click(await screen.findByRole('button', { name: '☆ Favorite' }));

  expect(await screen.findAllByText('Case already in favorites')).toHaveLength(1);
  expect(addFavorite).toHaveBeenCalledWith(42);
  expect(screen.queryByText('Could not update favorite')).toBeNull();
});

it("reports once that the filer's favorite cases could not load", async () => {
  localStorage.setItem('demo_role', 'attorney');
  vi.mocked(listFavorites).mockRejectedValueOnce(new Error('Network Error'));
  showCase(docket(true));

  expect(await screen.findAllByText('Could not load your favorite cases.')).toHaveLength(1);
  expect(screen.getByRole('button', { name: '☆ Favorite' })).toBeTruthy();
});

it('explains why more filings could not load when the server limits requests', async () => {
  localStorage.setItem('demo_role', 'public');
  const firstPage = Array.from({ length: 25 }, (_, index) => ({
    id: index + 1, status: 'accepted', case_title: 'Smith v. Jones', filing_description: `Filing ${index + 1}`,
    submitted_at: '2026-03-02T12:00:00Z', filing_date: '2026-03-02', reviewed_at: null, rejection_reason: null, documents: [],
  }));
  get.mockResolvedValueOnce({ data: docket(false) }).mockResolvedValueOnce({ data: firstPage });
  showCase(docket(false));
  const loadMore = await screen.findByRole('button', { name: 'Load more filings' });
  get.mockRejectedValueOnce({ response: { status: 429, data: {} } });

  fireEvent.click(loadMore);

  expect((await screen.findByRole('alert')).textContent).toBe('Too many requests. Please wait a moment and try again.');
});
