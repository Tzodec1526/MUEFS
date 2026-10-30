import { useContext, useState } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import type { LoadFailure } from '../../utils/errors';
import PageHeading, { HeadingFocusScope } from '../common/PageHeading';
import { CourtContext, CourtWorkspace, StaffCourtSelect } from './CourtSession';

afterEach(cleanup);

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
