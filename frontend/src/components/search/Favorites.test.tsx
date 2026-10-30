import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { listFavoriteCourts, listFavorites, removeFavorite, type FavoriteCase } from '../../api/favorites';
import { ToastProvider } from '../common/Toast';
import Favorites from './Favorites';

vi.mock('../../api/favorites', () => ({
  listFavorites: vi.fn(),
  removeFavorite: vi.fn(),
  listFavoriteCourts: vi.fn(),
  removeFavoriteCourt: vi.fn(),
}));

const OWN_REMOVAL_MESSAGE = 'Could not remove the favorite case. Please try again.';

function favorite(caseId: number, title: string): FavoriteCase {
  return {
    id: caseId * 10, case_id: caseId, case_number: `2026-${caseId}-CZ`, case_title: title,
    notes: null, created_at: '2026-09-01T12:00:00Z',
  };
}

function renderFavorites() {
  render(<MemoryRouter><ToastProvider><Favorites /></ToastProvider></MemoryRouter>);
}

function cardFor(title: string): HTMLElement {
  return screen.getByRole('heading', { name: title }).closest<HTMLElement>('.favorite-card')!;
}

beforeEach(() => {
  vi.mocked(listFavoriteCourts).mockResolvedValue({ favorites: [], total: 0 });
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('shows a retry, not an empty list, when favorites fail to load; retrying reloads them', async () => {
  vi.mocked(listFavorites)
    .mockRejectedValueOnce(new Error('Network Error'))
    .mockResolvedValueOnce({ favorites: [favorite(101, 'Smith v. Jones')], total: 1 });
  renderFavorites();

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Could not load your favorites. Please try again.');
  expect(screen.queryByText('No favorite cases yet')).toBeNull();

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  expect(await screen.findByRole('heading', { name: 'Smith v. Jones' })).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
  expect(listFavorites).toHaveBeenCalledTimes(2);
});

it('names a favorite court by county and court type in words', async () => {
  vi.mocked(listFavorites).mockResolvedValue({ favorites: [], total: 0 });
  vi.mocked(listFavoriteCourts).mockResolvedValue({ favorites: [{
    id: 1, court_id: 3, court_name: '3rd Circuit Court', county: 'Wayne', court_type: 'circuit', notes: null, created_at: '2026-09-01T12:00:00Z',
  }], total: 1 });
  renderFavorites();

  expect(await screen.findByText('Wayne County · Circuit Court')).toBeTruthy();
});

it('drops a removed case from the list and keeps the others', async () => {
  vi.mocked(listFavorites).mockResolvedValue({
    favorites: [favorite(101, 'Smith v. Jones'), favorite(202, 'Doe v. Roe')], total: 2,
  });
  vi.mocked(removeFavorite).mockResolvedValue();
  renderFavorites();
  await screen.findByRole('heading', { name: 'Smith v. Jones' });

  fireEvent.click(within(cardFor('Smith v. Jones')).getByRole('button', { name: 'Remove' }));

  await waitFor(() => expect(screen.queryByRole('heading', { name: 'Smith v. Jones' })).toBeNull());
  expect(removeFavorite).toHaveBeenCalledWith(101);
  expect(screen.getByRole('heading', { name: 'Doe v. Roe' })).toBeTruthy();
});

it('explains a failed removal itself when the server sent no detail, and keeps the case', async () => {
  vi.mocked(listFavorites).mockResolvedValue({ favorites: [favorite(101, 'Smith v. Jones')], total: 1 });
  vi.mocked(removeFavorite).mockRejectedValue(new Error('Network Error'));
  renderFavorites();

  fireEvent.click(await screen.findByRole('button', { name: 'Remove' }));

  expect(await screen.findByText(OWN_REMOVAL_MESSAGE)).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Smith v. Jones' })).toBeTruthy();
});

it("shows the server's explanation of a failed removal once, in place of its own", async () => {
  vi.mocked(listFavorites).mockResolvedValue({ favorites: [favorite(101, 'Smith v. Jones')], total: 1 });
  vi.mocked(removeFavorite).mockRejectedValue({ response: { status: 404, data: { detail: 'Favorite not found' } } });
  renderFavorites();

  fireEvent.click(await screen.findByRole('button', { name: 'Remove' }));

  expect(await screen.findAllByText('Favorite not found')).toHaveLength(1);
  expect(removeFavorite).toHaveBeenCalledWith(101);
  expect(screen.queryByText(OWN_REMOVAL_MESSAGE)).toBeNull();
});
