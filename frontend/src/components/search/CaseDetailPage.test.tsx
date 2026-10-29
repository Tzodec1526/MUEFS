import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from '../../api/client';
import type { CaseDocket } from '../../api/cases';
import { getCaseTypes, type CaseType } from '../../api/courts';
import { addFavorite, listFavorites } from '../../api/favorites';
import { ToastProvider } from '../common/Toast';
import CaseDetailPage from './CaseDetailPage';

// The real needsErrorMessage decides whether the page must explain a failure itself.
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
        <Routes><Route path="/cases/:caseId" element={<CaseDetailPage />} /></Routes>
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

it('adds no message of its own when the server already explained the favorite failure', async () => {
  localStorage.setItem('demo_role', 'attorney');
  vi.mocked(addFavorite).mockRejectedValue({ response: { status: 409, data: { detail: 'Case already in favorites' } } });
  showCase(docket(true));

  const favorite = await screen.findByRole('button', { name: '☆ Favorite' });
  fireEvent.click(favorite);
  // The button is disabled until the request settles.
  await waitFor(() => expect((favorite as HTMLButtonElement).disabled).toBe(false));

  expect(addFavorite).toHaveBeenCalledWith(42);
  expect(screen.queryByText('Could not update favorite')).toBeNull();
});
