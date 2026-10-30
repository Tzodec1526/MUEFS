import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { CanceledError } from 'axios';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { searchCases, type CaseSearchResult } from '../../api/cases';
import { listCourtDirectory } from '../../api/courts';
import { listFavorites } from '../../api/favorites';
import { CourtContext } from '../auth/CourtSession';
import { ToastProvider } from '../common/Toast';
import CaseSearch from './CaseSearch';

vi.mock('../../api/cases', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/cases')>(), searchCases: vi.fn(),
}));
vi.mock('../../api/courts', () => ({ listCourtDirectory: vi.fn() }));
vi.mock('../../api/favorites', () => ({ listFavorites: vi.fn(), addFavorite: vi.fn(), removeFavorite: vi.fn() }));

const smith: CaseSearchResult = {
  id: 42, case_number: '2026-000042-CZ', case_type_id: 11, title: 'Smith v. Jones', status: 'open',
  court_id: 3, court_name: 'Third Circuit Court', court_county: 'Wayne', filed_date: '2026-03-02',
  filing_date: '2026-03-02', participants: [{ party_name: 'Ann Smith', role: 'plaintiff' }],
};

function serveResults(cases: CaseSearchResult[], total = cases.length) {
  vi.mocked(searchCases).mockResolvedValue({ cases, total, page: 1, page_size: 25 });
}

function CurrentSearch() {
  return <output data-testid="current-search">{useLocation().search}</output>;
}

function openSearch(entry = '/cases/search') {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[entry]}>
        <CourtContext.Provider value={{ role: localStorage.getItem('demo_role'), courts: [], court: undefined, loading: false, selectCourt: () => {}, refresh: () => {} }}>
          <CaseSearch />
        </CourtContext.Provider>
        <CurrentSearch />
      </MemoryRouter>
    </ToastProvider>,
  );
}

const currentSearch = () => new URLSearchParams(screen.getByTestId('current-search').textContent ?? '');
const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement | HTMLSelectElement;
const lastQuery = () => vi.mocked(searchCases).mock.lastCall?.[0];

beforeEach(() => {
  localStorage.setItem('demo_role', 'public');
  vi.mocked(listCourtDirectory).mockResolvedValue([
    { id: 3, name: 'Third Circuit Court', county: 'Wayne' },
    { id: 9, name: 'Twenty-Second Circuit Court', county: 'Washtenaw' },
  ]);
  vi.mocked(listFavorites).mockResolvedValue({ favorites: [], total: 0 });
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  localStorage.clear();
});

it('queries the case number, party, court and page that the URL names', async () => {
  serveResults([smith], 30);
  openSearch('/cases/search?case=2026-000042&party=Smith&court=3&page=2');

  await screen.findByRole('link', { name: '2026-000042-CZ' });
  expect(searchCases).toHaveBeenCalledTimes(1);
  expect(lastQuery()).toEqual({ case_number: '2026-000042', party_name: 'Smith', court_id: 3, page: 2 });
  expect(field('Case number').value).toBe('2026-000042');
  expect(field('Party name').value).toBe('Smith');
  await waitFor(() => expect(field('Court').value).toBe('3'));
  expect(screen.getByRole('heading', { name: 'Results (30)' })).toBeTruthy();
});

it('puts the submitted case number, party and court in the URL and searches for them', async () => {
  serveResults([]);
  openSearch();
  await screen.findByRole('option', { name: 'Washtenaw — Twenty-Second Circuit Court' });

  fireEvent.change(field('Case number'), { target: { value: ' 2026-000042 ' } });
  fireEvent.change(field('Party name'), { target: { value: 'Smith' } });
  fireEvent.change(field('Court'), { target: { value: '9' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search' }));

  await waitFor(() => expect(lastQuery()).toEqual({
    case_number: '2026-000042', party_name: 'Smith', court_id: 9, page: 1,
  }));
  expect(Object.fromEntries(currentSearch())).toEqual({ case: '2026-000042', party: 'Smith', court: '9' });
});

it('leaves an empty filter out of the URL and the query', async () => {
  serveResults([]);
  openSearch();
  await waitFor(() => expect(searchCases).toHaveBeenCalledTimes(1));

  fireEvent.change(field('Party name'), { target: { value: 'Smith' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search' }));

  await waitFor(() => expect(lastQuery()).toEqual({
    case_number: undefined, party_name: 'Smith', court_id: undefined, page: 1,
  }));
  expect(Object.fromEntries(currentSearch())).toEqual({ party: 'Smith' });
});

it('runs the search again when the same search is submitted again', async () => {
  serveResults([smith]);
  openSearch('/cases/search?party=Smith');
  await screen.findByRole('link', { name: '2026-000042-CZ' });
  expect(searchCases).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole('button', { name: 'Search' }));

  await waitFor(() => expect(searchCases).toHaveBeenCalledTimes(2));
  expect(vi.mocked(searchCases).mock.calls[1][0]).toEqual(vi.mocked(searchCases).mock.calls[0][0]);
  expect(Object.fromEntries(currentSearch())).toEqual({ party: 'Smith' });
  await screen.findByRole('link', { name: '2026-000042-CZ' });
});

it('shows that a search is running until its results arrive', async () => {
  let answer: (value: Awaited<ReturnType<typeof searchCases>>) => void = () => {};
  vi.mocked(searchCases).mockReturnValue(new Promise(resolve => { answer = resolve; }));
  openSearch('/cases/search?party=Smith');

  const running = await screen.findByRole('button', { name: 'Searching...' }) as HTMLButtonElement;
  expect(running.disabled).toBe(true);
  expect(screen.getByText('Searching…')).toBeTruthy();

  answer({ cases: [smith], total: 1, page: 1, page_size: 25 });

  await screen.findByRole('link', { name: '2026-000042-CZ' });
  expect((screen.getByRole('button', { name: 'Search' }) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.queryByText('Searching…')).toBeNull();
});

it('says when a search finds no cases', async () => {
  serveResults([]);
  openSearch('/cases/search?case=9999');

  expect(await screen.findByText('No cases found. Check the number or name. Partial matches work.')).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Results (0)' })).toBeTruthy();
  expect(screen.queryByRole('table')).toBeNull();
});

it('shows a failed search inline and searches again on retry', async () => {
  serveResults([smith]);
  vi.mocked(searchCases).mockRejectedValueOnce(new Error('Network Error'));
  openSearch('/cases/search?party=Smith');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain("We couldn't reach the records system. Please try again.");
  expect(screen.queryByRole('table')).toBeNull();

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  await screen.findByRole('link', { name: '2026-000042-CZ' });
  const [[first], [second]] = vi.mocked(searchCases).mock.calls;
  expect(vi.mocked(searchCases).mock.calls).toHaveLength(2);
  expect(first).toMatchObject({ party_name: 'Smith' });
  expect(second).toEqual(first);
  expect(screen.queryByRole('alert')).toBeNull();
});

it('counts result pages with the page size the search reports', async () => {
  vi.mocked(searchCases).mockResolvedValue({ cases: [smith], total: 30, page: 1, page_size: 10 });
  openSearch('/cases/search?party=Smith');

  expect(await screen.findByText('Page 1 of 3')).toBeTruthy();
});

it('labels every result cell with its column, so a row still reads when it stacks on a phone', async () => {
  localStorage.setItem('demo_role', 'attorney');
  serveResults([smith]);
  openSearch('/cases/search?party=Smith');

  const table = await screen.findByRole('table');
  const columns = within(table).getAllByRole('columnheader').map(cell => cell.textContent);
  const cells = within(within(table).getAllByRole('row')[1]).getAllByRole('cell');
  expect(columns).toEqual(['', 'Case number', 'Court', 'Title', 'Status', 'Filed date', 'Parties']);
  expect(cells.map(cell => cell.getAttribute('data-label'))).toEqual([null, ...columns.slice(1)]);
  expect(cells[5].textContent).toBe('Mar 2, 2026');
});

it('names party roles in words, not as stored values', async () => {
  serveResults([{ ...smith, participants: [
    { party_name: 'Ann Smith', role: 'plaintiff' }, { party_name: 'Jane Doe', role: 'attorney_plaintiff' },
  ] }]);
  openSearch('/cases/search?party=Smith');

  expect(await screen.findByText('Ann Smith, Plaintiff; Jane Doe, Attorney (Plaintiff)')).toBeTruthy();
  expect(document.body.textContent).not.toContain('attorney_plaintiff');
});

it('says in plain words when the court has not confirmed a filed date', async () => {
  serveResults([{ ...smith, filing_date: null, filed_date: '2026-03-02T12:00:00Z' }]);
  openSearch('/cases/search?party=Smith');

  expect(await screen.findByText('Mar 2, 2026 (not yet confirmed by the court)')).toBeTruthy();
  expect(screen.queryByText(/unverified/)).toBeNull();
});

it('offers a labeled Copy link once there is a search to share', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  serveResults([smith]);
  openSearch('/cases/search?party=Smith');

  fireEvent.click(await screen.findByRole('button', { name: 'Copy link' }));

  await screen.findByText('Search link copied to clipboard');
  expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/cases/search?party=Smith`);
});

it('has no link to copy before a search', async () => {
  serveResults([]);
  openSearch('/cases/search');

  await screen.findByRole('heading', { name: 'Recent public filings' });
  expect(screen.queryByRole('button', { name: 'Copy link' })).toBeNull();
});

it('introduces the search in one plain line', async () => {
  serveResults([]);
  openSearch('/cases/search');

  expect((await screen.findByRole('heading', { level: 1 })).textContent).toBe('Case search');
  expect(screen.getByText('Partial names and case numbers work. Sealed cases are not listed.')).toBeTruthy();
  expect(document.body.textContent).not.toMatch(/Statewide|vendor portal|file motions/);
});

it("links each result's case number to its docket", async () => {
  serveResults([smith, { ...smith, id: 43, case_number: '2026-000043-CZ', title: 'Doe v. Roe' }]);
  openSearch('/cases/search?party=Smith');

  expect((await screen.findByRole('link', { name: '2026-000042-CZ' })).getAttribute('href')).toBe('/cases/42');
  expect(screen.getByRole('link', { name: '2026-000043-CZ' }).getAttribute('href')).toBe('/cases/43');
});

it("reports once that the filer's favorite cases could not load", async () => {
  localStorage.setItem('demo_role', 'attorney');
  serveResults([smith]);
  vi.mocked(listFavorites).mockRejectedValue(new Error('Network Error'));
  openSearch('/cases/search?party=Smith');

  expect(await screen.findAllByText('Could not load your favorite cases.')).toHaveLength(1);
});

it('stays silent when the favorite cases request was cancelled', async () => {
  localStorage.setItem('demo_role', 'attorney');
  serveResults([smith]);
  vi.mocked(listFavorites).mockRejectedValue(new CanceledError('The signed-in account changed.'));
  openSearch('/cases/search?party=Smith');

  await screen.findByRole('link', { name: '2026-000042-CZ' });
  await waitFor(() => expect(listFavorites).toHaveBeenCalled());
  expect(screen.queryByText('Could not load your favorite cases.')).toBeNull();
});
