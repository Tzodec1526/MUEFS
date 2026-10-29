// @vitest-environment jsdom
import { useContext, useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
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
