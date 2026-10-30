import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { listCourts, type Court } from '../../api/courts';
import { addFavoriteCourt, listFavoriteCourts } from '../../api/favorites';
import { ToastProvider } from '../common/Toast';
import CourtSelector from './CourtSelector';

vi.mock('../../api/courts', () => ({ listCourts: vi.fn() }));
vi.mock('../../api/favorites', () => ({
  listFavoriteCourts: vi.fn(),
  addFavoriteCourt: vi.fn(),
  removeFavoriteCourt: vi.fn(),
}));

const STATEWIDE_FAILURE = "We couldn't load the statewide and appellate courts. Please try again.";

function court(id: number, name: string, courtType: string): Court {
  return {
    id, name, county: 'Wayne', court_type: courtType, division: null, address: null, city: 'Detroit',
    state: 'MI', zip_code: null, phone: null, cms_type: null, is_efiling_enabled: true,
  };
}

/** Serve each tier's requests in order; a thrown entry fails that request. */
function serveCourts(responses: Record<'appellate' | 'trial', Array<Court[] | Error>>) {
  vi.mocked(listCourts).mockImplementation(async (params) => {
    const tier = params?.tier as 'appellate' | 'trial';
    const next = responses[tier][callsFor(tier).length - 1];
    if (next instanceof Error) throw next;
    return { courts: next, total: next.length };
  });
}

function callsFor(tier: string) {
  return vi.mocked(listCourts).mock.calls.filter(([params]) => params?.tier === tier);
}

function renderSelector(onSelect = vi.fn()) {
  render(<ToastProvider><CourtSelector selectedCourtId={null} onSelect={onSelect} /></ToastProvider>);
}

beforeEach(() => {
  vi.mocked(listFavoriteCourts).mockResolvedValue({ favorites: [], total: 0 });
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('replaces the court lists with a retry when the statewide courts fail to load', async () => {
  serveCourts({ appellate: [new Error('Network Error')], trial: [[court(3, 'Third Circuit Court', 'circuit')]] });
  renderSelector();

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain(STATEWIDE_FAILURE);
  expect(within(alert).getByRole('button', { name: 'Retry' })).toBeTruthy();

  // Even once the trial courts arrive, a missing statewide group must not look like an empty one.
  await waitFor(() => expect(callsFor('trial')).toHaveLength(1));
  await act(async () => {});
  expect(screen.queryByText('Third Circuit Court')).toBeNull();
  expect(screen.getByRole('alert').textContent).toContain(STATEWIDE_FAILURE);
});

it('selects a court with its own button, beside (not around) the favorite star', async () => {
  serveCourts({ appellate: [[]], trial: [[{ ...court(3, 'Third Circuit Court', 'circuit'), address: '2 Woodward Ave' }]] });
  vi.mocked(addFavoriteCourt).mockResolvedValue({
    id: 1, court_id: 3, court_name: 'Third Circuit Court', county: 'Wayne', court_type: 'circuit', notes: null,
    created_at: '2026-09-01T12:00:00Z',
  });
  const onSelect = vi.fn();
  renderSelector(onSelect);

  const select = await screen.findByRole('button', { name: 'Third Circuit Court' });
  const star = screen.getByRole('button', { name: 'Add Third Circuit Court to favorites' });
  // Neither control is nested in another interactive element.
  for (const control of [select, star]) {
    expect(control.parentElement!.closest('button, [role="button"], a, [tabindex]')).toBeNull();
  }
  expect(select.getAttribute('aria-pressed')).toBe('false');
  expect(select.getAttribute('aria-describedby')?.split(' ').map(id => document.getElementById(id)?.textContent))
    .toEqual(['Wayne County · Circuit Court', '2 Woodward Ave']);

  fireEvent.click(star);
  await waitFor(() => expect(addFavoriteCourt).toHaveBeenCalledWith(3));
  expect(onSelect).not.toHaveBeenCalled();

  fireEvent.click(select);
  expect(onSelect).toHaveBeenCalledWith(3, 'Third Circuit Court');
});

it('reloads both the statewide and the trial courts on retry', async () => {
  serveCourts({
    appellate: [new Error('Network Error'), [court(90, 'Michigan Court of Appeals', 'court_of_appeals')]],
    trial: [[court(3, 'Third Circuit Court', 'circuit')], [court(4, '22nd Circuit Court', 'circuit')]],
  });
  renderSelector();
  const alert = await screen.findByRole('alert');
  await waitFor(() => expect(callsFor('trial')).toHaveLength(1));

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  expect(await screen.findByText('Michigan Court of Appeals')).toBeTruthy();
  expect(await screen.findByText('22nd Circuit Court')).toBeTruthy();
  expect(screen.queryByText('Third Circuit Court')).toBeNull();
  expect(screen.queryByRole('alert')).toBeNull();
  expect(callsFor('appellate')).toHaveLength(2);
  expect(callsFor('trial')).toHaveLength(2);
});

it("reports once that the filer's favorite courts could not load", async () => {
  serveCourts({ appellate: [[]], trial: [[]] });
  vi.mocked(listFavoriteCourts).mockRejectedValue(new Error('Network Error'));
  renderSelector();

  expect(await screen.findAllByText('Could not load your favorite courts.')).toHaveLength(1);
});
