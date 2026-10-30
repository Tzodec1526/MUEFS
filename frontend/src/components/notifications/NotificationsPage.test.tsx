import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from '../../api/client';
import { CourtContext } from '../auth/CourtSession';
import NotificationsPage from './NotificationsPage';

vi.mock('../../api/client', async (importOriginal) => {
  const offline = () => Promise.reject(new Error('Unexpected API request in a component test'));
  return {
    ...await importOriginal<typeof import('../../api/client')>(),
    apiClient: { get: vi.fn(offline), post: vi.fn(offline), put: vi.fn(offline), patch: vi.fn(offline), delete: vi.fn(offline) },
  };
});

const get = apiClient.get as unknown as Mock<(url: string) => Promise<{ data: unknown }>>;
const post = apiClient.post as unknown as Mock<(url: string, body: unknown) => Promise<{ data: unknown }>>;

const notice = {
  id: 7, filing_envelope_id: 12, delivery_id: null, type: 'filing_accepted', subject: 'Filing #12 accepted',
  body: 'The clerk accepted filing #12.', delivery_status: 'failed', created_at: '2026-03-02T12:00:00Z',
  email_recipient: 'pat@example.com', attempt_count: 1, last_error: null, sent_at: null, next_attempt_at: null,
};
const history = {
  events: [{ id: 1, attempt_number: 1, outcome: 'failed', occurred_at: '2026-03-02T12:01:00Z', detail: null, smtp_code: 550 }],
  total: 1, page: 1, message_id: null, can_retry: true,
};

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('shows a refused request for another email next to the form, without a retry button', async () => {
  get.mockImplementation(async (url) => {
    if (url === '/notifications') return { data: { notifications: [notice], total: 1, page_size: 25, email_enabled: true } };
    if (url === '/notifications/7/delivery') return { data: history };
    throw new Error(`Unexpected request: ${url}`);
  });
  post.mockRejectedValue({ response: { status: 403, data: {} } });
  render(
    <MemoryRouter initialEntries={['/notifications']}>
      <CourtContext.Provider value={{
        userId: 1, role: 'attorney', courts: [], court: undefined, loading: false,
        selectCourt: () => {}, refresh: () => {},
      }}>
        <NotificationsPage />
      </CourtContext.Provider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole('button', { name: 'Email history' }));
  fireEvent.change(await screen.findByLabelText('Reason for requesting another email'), { target: { value: 'Address corrected' } });

  fireEvent.click(screen.getByRole('button', { name: 'Queue another email' }));

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toBe('You do not have permission to do that.');
  expect(within(alert).queryByRole('button')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
  expect(post).toHaveBeenCalledWith('/notifications/7/retry', { reason: 'Address corrected' });
  expect(screen.getByRole('button', { name: 'Queue another email' })).toBeTruthy();
});
