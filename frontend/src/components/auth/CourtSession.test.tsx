import { useContext, useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from '../../api/client';
import type { LoadFailure } from '../../utils/errors';
import PageHeading, { HeadingFocusScope } from '../common/PageHeading';
import { CourtContext, CourtSession, CourtWorkspace, StaffCourtSelect } from './CourtSession';

vi.mock('../../api/client', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/client')>(), apiClient: { get: vi.fn() },
}));

const getProfile = apiClient.get as unknown as Mock<() => Promise<{ data: unknown }>>;

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.resetAllMocks();
});

const courts = [
  { court_id: 3, role: 'clerk', court_name: 'Wayne Circuit' },
  { court_id: 9, role: 'clerk', court_name: 'Washtenaw Circuit' },
];

/** Same shape as ReviewQueue, ClerkDashboard and the other court pages: the select lives inside the page. */
function CourtPage() {
  const { court } = useContext(CourtContext)!;
  const [note, setNote] = useState('');
  return <>
    <StaffCourtSelect />
    <p>Queue for {court?.court_name}</p>
    <label>Note<input value={note} onChange={event => setNote(event.target.value)} /></label>
  </>;
}

function Workspace() {
  const [selected, setSelected] = useState(3);
  const court = courts.find(item => item.court_id === selected);
  return <CourtContext.Provider value={{
    userId: 2, role: 'clerk', courts, court, loading: false, selectCourt: setSelected, refresh: () => {},
  }}>
    <CourtWorkspace><CourtPage /></CourtWorkspace>
  </CourtContext.Provider>;
}

const courtSelect = () => screen.getByLabelText('Working court') as HTMLSelectElement;
const note = () => screen.getByLabelText('Note') as HTMLInputElement;

function showWorkspace(state: { loading?: boolean; error?: LoadFailure }, refresh = () => {}) {
  return render(
    <MemoryRouter>
      <HeadingFocusScope>
        <CourtContext.Provider value={{
          userId: 2, role: 'clerk', courts: [], court: undefined, loading: false, selectCourt: () => {}, refresh, ...state,
        }}>
          <CourtWorkspace><p>The court page</p></CourtWorkspace>
        </CourtContext.Provider>
      </HeadingFocusScope>
    </MemoryRouter>,
  );
}

it('names the court workspace while its assignments load', () => {
  showWorkspace({ loading: true });

  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Loading court workspace');
  expect(screen.getByRole('status').textContent).toBe('Loading court assignments…');
  expect(document.title).toBe('Loading court workspace · MUEFS');
});

it('heads a failed court workspace with one h1, an alert and a retry', () => {
  const refresh = vi.fn();
  showWorkspace({ error: { message: 'Could not verify court assignments.', retry: true } }, refresh);

  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Court workspace not loaded');
  expect(document.title).toBe('Court workspace not loaded · MUEFS');
  const alert = screen.getByRole('alert');
  expect(alert.textContent).toContain('Could not verify court assignments.');

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  expect(refresh).toHaveBeenCalledTimes(1);
});

it('still moves focus to the court page heading after a navigation that waited on the workspace', async () => {
  function Page() {
    return <PageHeading>Review queue</PageHeading>;
  }
  function Shell() {
    const [loading, setLoading] = useState(false);
    return (
      <CourtContext.Provider value={{
        userId: 2, role: 'clerk', courts: [{ court_id: 3, role: 'clerk', court_name: 'Wayne' }],
        court: { court_id: 3, role: 'clerk', court_name: 'Wayne' }, loading, selectCourt: () => {}, refresh: () => {},
      }}>
        <Routes>
          <Route path="/" element={<><PageHeading>Dashboard</PageHeading><Link to="/queue" onClick={() => setLoading(true)}>Queue</Link></>} />
          <Route path="/queue" element={<CourtWorkspace><Page /></CourtWorkspace>} />
        </Routes>
        <button onClick={() => setLoading(false)}>Assignments loaded</button>
      </CourtContext.Provider>
    );
  }
  render(<MemoryRouter><HeadingFocusScope><Shell /></HeadingFocusScope></MemoryRouter>);

  fireEvent.click(screen.getByRole('link', { name: 'Queue' }));
  await screen.findByText('Loading court assignments…');
  fireEvent.click(screen.getByRole('button', { name: 'Assignments loaded' }));

  expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: 'Review queue' }));
});

const staffProfile = { data: {
  id: 2, user_type: 'clerk', court_assignments: [{ court_id: 3, role: 'clerk', court_name: 'Wayne Circuit' }],
} };

function renderSession(initialEntries = ['/queue']) {
  localStorage.setItem('demo_role', 'clerk');
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <HeadingFocusScope>
        <CourtSession>
          <Routes>
            <Route path="/" element={<><PageHeading>Dashboard</PageHeading><Link to="/queue">Queue</Link></>} />
            <Route path="/queue" element={<CourtWorkspace><PageHeading>Review queue</PageHeading></CourtWorkspace>} />
          </Routes>
        </CourtSession>
      </HeadingFocusScope>
    </MemoryRouter>,
  );
}

const failedHeading = () => screen.findByRole('heading', { level: 1, name: 'Court workspace not loaded' });

async function retry() {
  fireEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Retry' }));
  await screen.findByRole('heading', { level: 1, name: 'Loading court workspace' });
}

it('puts focus back on the error heading when a retry fails again on the first page load', async () => {
  getProfile.mockRejectedValue(new Error('offline'));
  renderSession();
  expect(document.activeElement).not.toBe(await failedHeading());

  await retry();

  const heading = await failedHeading();
  await waitFor(() => expect(document.activeElement).toBe(heading));
});

it('puts focus back on the error heading when a retry fails again on the same navigation', async () => {
  let failFirstLoad = (_reason: Error) => {};
  getProfile.mockReturnValueOnce(new Promise((_resolve, reject) => { failFirstLoad = reject; }));
  renderSession(['/']);
  fireEvent.click(screen.getByRole('link', { name: 'Queue' }));
  await screen.findByRole('heading', { level: 1, name: 'Loading court workspace' });
  failFirstLoad(new Error('offline'));
  const first = await failedHeading();
  await waitFor(() => expect(document.activeElement).toBe(first));
  getProfile.mockRejectedValue(new Error('offline'));

  await retry();

  const heading = await failedHeading();
  await waitFor(() => expect(document.activeElement).toBe(heading));
});

it('keeps moving focus to the error heading across repeated failures', async () => {
  getProfile.mockRejectedValue(new Error('offline'));
  renderSession();
  await failedHeading();
  await retry();
  const second = await failedHeading();
  await waitFor(() => expect(document.activeElement).toBe(second));

  await retry();

  const third = await failedHeading();
  await waitFor(() => expect(document.activeElement).toBe(third));
});

it('moves focus to the court page heading when a retry succeeds', async () => {
  getProfile.mockRejectedValueOnce(new Error('offline'));
  renderSession();
  await failedHeading();
  getProfile.mockResolvedValueOnce(staffProfile);

  await retry();

  const heading = await screen.findByRole('heading', { level: 1, name: 'Review queue' });
  await waitFor(() => expect(document.activeElement).toBe(heading));
});

it('does not move focus to the page heading when nothing asked for a reload', async () => {
  getProfile.mockResolvedValue(staffProfile);
  renderSession();

  const heading = await screen.findByRole('heading', { level: 1, name: 'Review queue' });

  expect(document.activeElement).not.toBe(heading);
});

it('keeps keyboard focus on the working-court select while the page resets for the new court', () => {
  render(<Workspace />);
  fireEvent.change(note(), { target: { value: 'Wayne only' } });
  courtSelect().focus();

  fireEvent.change(courtSelect(), { target: { value: '9' } });

  expect(screen.getByText('Queue for Washtenaw Circuit')).toBeTruthy();
  // State from the prior court is still discarded...
  expect(note().value).toBe('');
  // ...but keyboard focus stays on the select the user just changed.
  expect(courtSelect().value).toBe('9');
  expect(document.activeElement).toBe(courtSelect());
});

it('does not pull focus to the select when the court changes while something else has focus', () => {
  render(<Workspace />);
  note().focus();

  fireEvent.change(courtSelect(), { target: { value: '9' } });

  expect(screen.getByText('Queue for Washtenaw Circuit')).toBeTruthy();
  expect(document.activeElement).not.toBe(courtSelect());
});
