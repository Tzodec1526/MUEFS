import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { listNotifications } from '../../api/notifications';
import { CourtContext } from '../auth/CourtSession';
import NotificationBell from './NotificationBell';

vi.mock('../../api/notifications', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/notifications')>(), listNotifications: vi.fn(),
}));

beforeEach(() => {
  localStorage.setItem('demo_role', 'attorney');
  vi.mocked(listNotifications).mockResolvedValue({
    notifications: [{
      id: 1, filing_envelope_id: 11, delivery_id: null, type: 'filing_accepted', subject: 'Filing #11 accepted',
      body: 'The clerk accepted your filing.', delivery_status: 'sent', created_at: '2026-09-28T12:00:00Z',
      email_recipient: null, attempt_count: 1, last_error: null, sent_at: null, next_attempt_at: null,
    }],
    total: 1, page_size: 25, email_enabled: false,
  });
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  localStorage.clear();
});

function renderBell() {
  render(<MemoryRouter>
    <CourtContext.Provider value={{ role: localStorage.getItem('demo_role'), courts: [], court: undefined, loading: false, selectCourt: () => {}, refresh: () => {} }}>
      <NotificationBell />
    </CourtContext.Provider>
    <button type="button">Elsewhere</button>
  </MemoryRouter>);
  return screen.getByRole('button', { name: 'Notifications' });
}

async function openBell() {
  const toggle = renderBell();
  toggle.focus();
  fireEvent.click(toggle);
  await screen.findByText('Filing #11 accepted');
  return toggle;
}

it('opens as a disclosure controlled by its button, not as a dialog', async () => {
  const toggle = await openBell();

  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  expect(screen.queryByRole('dialog')).toBeNull();
  const panel = document.getElementById(toggle.getAttribute('aria-controls')!);
  expect(panel?.textContent).toContain('Recent notifications');
});

it('closes on Escape and returns focus to its button', async () => {
  const toggle = await openBell();
  const link = screen.getByRole('link', { name: 'View filing history' });
  link.focus();

  fireEvent.keyDown(link, { key: 'Escape' });

  expect(screen.queryByText('Recent notifications')).toBeNull();
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  expect(document.activeElement).toBe(toggle);
});

it('stays open while focus moves inside it and closes once focus leaves it', async () => {
  await openBell();
  act(() => screen.getByRole('link', { name: 'View filing history' }).focus());
  act(() => screen.getByRole('link', { name: /All notices/ }).focus());
  expect(screen.getByText('Recent notifications')).toBeTruthy();

  const elsewhere = screen.getByRole('button', { name: 'Elsewhere' });
  act(() => elsewhere.focus());

  expect(screen.queryByText('Recent notifications')).toBeNull();
  expect(document.activeElement).toBe(elsewhere);
});
