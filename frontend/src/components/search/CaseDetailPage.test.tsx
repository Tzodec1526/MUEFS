import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { CanceledError } from 'axios';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
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

const serve = (responses: Record<string, () => Promise<unknown>>) => get.mockImplementation(async (url) => {
  if (!(url in responses)) throw new Error(`Unexpected request: ${url}`);
  return { data: await responses[url]() };
});

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

    await screen.findByRole('link', { name: 'File in this case' });
    const base = '/filing/new?case_id=42&court_id=3&case_type_id=11';
    expect(filingLinks()).toEqual([base, `${base}&service_only=true`]);
    for (const href of filingLinks()) {
      expect(new URL(href, 'http://localhost').searchParams.has('case_title')).toBe(false);
    }
    expect(screen.queryByText(PARTICIPATION_NOTICE)).toBeNull();
  });
});

it('shows the case number once, under the title, with the status beside it', async () => {
  localStorage.setItem('demo_role', 'public');
  showCase(docket(false));

  const number = await screen.findByText(/^2026-000042-CZ/);
  expect(number.textContent).toBe('2026-000042-CZ open');
  expect(number.previousElementSibling).toBe(screen.getByRole('heading', { level: 1, name: 'Smith v. Jones' }));
  expect(screen.getAllByText(/2026-000042-CZ/)).toHaveLength(1);
  expect(screen.queryByText('Status')).toBeNull();
});

it('heads the filings list "Docket" and steps down one heading level from the title', async () => {
  localStorage.setItem('demo_role', 'public');
  showCase(docket(false));

  expect(await screen.findByRole('heading', { level: 2, name: 'Docket' })).toBeTruthy();
  expect(screen.getAllByRole('heading').map(heading => heading.tagName)).toEqual(['H1', 'H2', 'H2', 'H2']);
});

it('says in plain words when the court has not confirmed the filing date', async () => {
  localStorage.setItem('demo_role', 'public');
  showCase({ ...docket(false), filing_date: null, filed_date: '2026-03-02T12:00:00Z' });

  const label = await screen.findByText('Date on record (not yet confirmed by the court)');
  expect(label.nextElementSibling?.textContent).toBe('Mar 2, 2026');
  expect(screen.getByText('Not established')).toBeTruthy();
  expect(document.body.textContent).not.toMatch(/calendar-verified|Stored date/i);
});

it('leaves out the unconfirmed date once the court has set a filing date', async () => {
  localStorage.setItem('demo_role', 'public');
  showCase(docket(false));

  await screen.findByText('Mar 2, 2026');
  expect(screen.queryByText(/not yet confirmed/)).toBeNull();
});

it('offers a labeled Copy link', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  localStorage.setItem('demo_role', 'public');
  showCase(docket(false));

  fireEvent.click(await screen.findByRole('button', { name: 'Copy link' }));

  await screen.findByText('Case link copied to clipboard');
  expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/cases/42`);
});

it('does not announce the participation note as a live update', async () => {
  localStorage.setItem('demo_role', 'attorney');
  showCase(docket(false));

  expect((await screen.findByText(PARTICIPATION_NOTICE)).closest('[role],[aria-live]')).toBeNull();
});

it("reports once that the court's name could not load, and keeps the rest of the docket", async () => {
  localStorage.setItem('demo_role', 'public');
  showCase(docket(false));
  serve({
    '/cases/42': async () => docket(false), '/cases/42/filings': async () => [],
    '/courts/3': async () => { throw new Error('Network Error'); },
  });

  expect(await screen.findAllByText("Could not load the court's name.")).toHaveLength(1);
  expect(screen.getByText('Court #3')).toBeTruthy();
  expect(screen.getByText('General Civil')).toBeTruthy();
});

it('reports once that the case type name could not load, and keeps the court name', async () => {
  localStorage.setItem('demo_role', 'public');
  showCase(docket(false));
  vi.mocked(getCaseTypes).mockRejectedValue(new Error('Network Error'));

  expect(await screen.findAllByText('Could not load the case type name.')).toHaveLength(1);
  expect(screen.getByText('Third Circuit Court')).toBeTruthy();
});

it('stays silent when a label lookup was cancelled', async () => {
  localStorage.setItem('demo_role', 'public');
  showCase(docket(false));
  vi.mocked(getCaseTypes).mockRejectedValue(new CanceledError());

  await screen.findByText('Third Circuit Court');
  expect(screen.queryByText('Could not load the case type name.')).toBeNull();
});

it('ignores a failed lookup for a case the reader has already left', async () => {
  localStorage.setItem('demo_role', 'public');
  let failFirstCourtLookup: (reason: Error) => void = () => {};
  const courtLookups = [
    () => new Promise((_, reject) => { failFirstCourtLookup = reject; }),
    async () => ({ name: 'Third Circuit Court' }),
  ];
  serve({
    '/cases/42': async () => docket(false), '/cases/42/filings': async () => [],
    '/courts/3': () => courtLookups.shift()!(),
    '/cases/43': async () => ({ ...docket(false), id: 43, title: 'Doe v. Roe' }), '/cases/43/filings': async () => [],
  });
  vi.mocked(getCaseTypes).mockResolvedValue([civil]);
  render(
    <MemoryRouter initialEntries={['/cases/42']}>
      <ToastProvider>
        <CourtContext.Provider value={{ role: 'public', courts: [], court: undefined, loading: false, selectCourt: () => {}, refresh: () => {} }}>
          <Link to="/cases/43">Next case</Link>
          <Routes><Route path="/cases/:caseId" element={<CaseDetailPage />} /></Routes>
        </CourtContext.Provider>
      </ToastProvider>
    </MemoryRouter>,
  );
  await waitFor(() => expect(get).toHaveBeenCalledWith('/courts/3', expect.anything()));

  fireEvent.click(screen.getByRole('link', { name: 'Next case' }));
  await screen.findByRole('heading', { level: 1, name: 'Doe v. Roe' });
  failFirstCourtLookup(new Error('Network Error'));

  await screen.findByText('Third Circuit Court');
  await new Promise(resolve => { setTimeout(resolve); });
  expect(screen.queryByText("Could not load the court's name.")).toBeNull();
  expect(within(document.body).queryByRole('alert')).toBeNull();
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
