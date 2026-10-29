// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import {
  batchReview, getClerkQueue, getFiling, reviewFiling, type ClerkQueue, type FilingEnvelope, type FilingSummary,
} from '../../api/filings';
import { CourtContext } from '../auth/CourtSession';
import ReviewQueue from './ReviewQueue';

vi.mock('../../api/filings', () => ({
  getClerkQueue: vi.fn(), getFiling: vi.fn(), reviewFiling: vi.fn(), batchReview: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function summary(id: number): FilingSummary {
  return {
    id, court_id: 3, case_id: null, filer_id: 1, status: 'submitted', case_title: `Case ${id}`,
    filing_description: null, submitted_at: '2026-09-28T12:00:00Z', rejection_reason: null,
    fee_waiver_requested: false, fee_waiver_granted: null, created_at: '2026-09-28T12:00:00Z',
    updated_at: '2026-09-28T12:00:00Z', submission_count: 1, document_count: 0,
  };
}

function envelope(id: number): FilingEnvelope {
  return {
    ...summary(id), submission_token: `s-${id}`, details_token: `d-${id}`, case_type_id: 11,
    filing_type: 'initial', payment_id: null, reviewed_at: null, fee_waiver_reason: null,
    fee_waiver_referred_at: null, fee_waiver_decided_at: null, fee_waiver_amount_due_cents: null,
    documents: [], filing_date: null, filing_date_basis: null,
  };
}

/** Each load returns a fresh response, as the API does; later loads repeat the last list. */
function serveQueues(...lists: number[][]) {
  let call = 0;
  vi.mocked(getClerkQueue).mockImplementation(async (): Promise<ClerkQueue> => {
    const ids = lists[Math.min(call++, lists.length - 1)];
    return {
      filings: ids.map(summary), total: ids.length, submitted_count: ids.length, under_review_count: 0,
      waiting_48h: 0, oldest_submitted_at: null, as_of: '2026-09-28T13:00:00Z',
    };
  });
}

function openQueue() {
  const court = { court_id: 3, role: 'clerk', court_name: 'Wayne Circuit' };
  return render(
    <MemoryRouter>
      <CourtContext.Provider value={{
        userId: 2, role: 'clerk', courts: [court], court, loading: false, selectCourt: () => {}, refresh: () => {},
      }}>
        <ReviewQueue />
      </CourtContext.Provider>
    </MemoryRouter>,
  );
}

const row = (id: number) => document.getElementById(`queue-filing-${id}`);

async function openReview(id: number) {
  vi.mocked(getFiling).mockResolvedValue(envelope(id));
  fireEvent.click(await screen.findByText(`Case ${id}`));
  await screen.findByRole('heading', { name: `Filing #${id}` });
}

it('moves focus to the next filing after accepting one', async () => {
  serveQueues([11, 12, 13], [11, 13]);
  vi.mocked(reviewFiling).mockResolvedValue(envelope(12));
  openQueue();
  await openReview(12);
  const accept = screen.getByRole('button', { name: 'Accept' });
  accept.focus();

  fireEvent.click(accept);

  await waitFor(() => expect(screen.queryByText('Case 12')).toBeNull());
  await waitFor(() => expect(document.activeElement).toBe(row(13)));
  expect(reviewFiling).toHaveBeenCalledWith(expect.objectContaining({ id: 12 }), 'accept', undefined);
});

it.each([
  ['Return for Correction', 'return'],
  ['Reject', 'reject'],
])('moves focus to the queue heading after "%s" on the last filing', async (buttonName, action) => {
  serveQueues([11], []);
  vi.mocked(reviewFiling).mockResolvedValue(envelope(11));
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  openQueue();
  await openReview(11);
  fireEvent.change(screen.getByLabelText('Reason (required for reject/return)'),
    { target: { value: 'Missing required documents' } });
  const button = screen.getByRole('button', { name: buttonName });
  button.focus();

  fireEvent.click(button);

  await screen.findByText('No filings match these filters in this court.');
  await waitFor(() => expect(document.activeElement)
    .toBe(screen.getByRole('heading', { name: 'Clerk Review Queue' })));
  expect(reviewFiling).toHaveBeenCalledWith(expect.objectContaining({ id: 11 }), action, 'Missing required documents');
  confirm.mockRestore();
});

it('keeps focus in the queue after a batch accept', async () => {
  serveQueues([11, 12, 13], [13]);
  vi.mocked(batchReview).mockResolvedValue({ succeeded: [11, 12], failed: [], errors: {} });
  openQueue();
  fireEvent.click(await screen.findByRole('checkbox', { name: 'Select filing 11' }));
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select filing 12' }));
  const acceptSelected = screen.getByRole('button', { name: 'Accept 2 Filing(s)' });
  acceptSelected.focus();

  fireEvent.click(acceptSelected);

  await waitFor(() => expect(document.activeElement).toBe(row(13)));
  expect(batchReview).toHaveBeenCalledWith([{ id: 11, submission_count: 1 }, { id: 12, submission_count: 1 }], 'accept');
});

it.each([
  ['a raw request error', new Error('Request failed with status code 409'),
    'Could not accept the selected filings. Refresh the queue to check their current status before trying again.'],
  ['a server explanation', { response: { status: 409, data: { detail: 'Filing #11 changed after it was listed.' } } },
    'Filing #11 changed after it was listed.'],
])('explains a failed batch accept from %s without showing request internals', async (_, failure, message) => {
  serveQueues([11, 12]);
  vi.mocked(batchReview).mockRejectedValue(failure);
  openQueue();
  fireEvent.click(await screen.findByRole('checkbox', { name: 'Select filing 11' }));

  fireEvent.click(screen.getByRole('button', { name: 'Accept 1 Filing(s)' }));

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toBe(`${message}Dismiss`);
  await waitFor(() => expect(document.activeElement).toBe(row(11)));
});

it('returns focus to the open review when an action fails', async () => {
  serveQueues([11]);
  vi.mocked(reviewFiling).mockImplementation(async () => {
    // Browsers drop focus from the button once it is disabled for the running action.
    (document.activeElement as HTMLElement | null)?.blur();
    throw new Error('Network Error');
  });
  openQueue();
  await openReview(11);
  const accept = screen.getByRole('button', { name: 'Accept' });
  accept.focus();

  fireEvent.click(accept);

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Failed to accept filing #11: the request did not complete.');
  expect(alert.textContent).not.toContain('Network Error');
  expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Filing #11' }));
});

it('names its declarative filter form apart from the imperative queue tool', async () => {
  serveQueues([11]);
  const { container } = openQueue();
  await screen.findByText('Case 11');

  expect(container.querySelector('form[toolname="review_queue_form"]')).not.toBeNull();
  expect(container.querySelector('form[toolname="get_clerk_review_queue"]')).toBeNull();
});

/** Submit the filter form as an agent would, with SubmitEvent.respondWith() available. */
function submitFilters(agentInvoked: boolean) {
  const form = document.querySelector('form[toolname="review_queue_form"]') as HTMLFormElement;
  const event = new Event('submit', { bubbles: true, cancelable: true });
  const answers: Promise<unknown>[] = [];
  if (agentInvoked) {
    Object.defineProperty(event, 'agentInvoked', { value: true });
    Object.defineProperty(event, 'respondWith', { value: (answer: Promise<unknown>) => answers.push(answer) });
  }
  fireEvent(form, event);
  return answers;
}

it('answers an agent filter submission with the same result as get_clerk_review_queue', async () => {
  serveQueues([11, 12], [12]);
  openQueue();
  await waitFor(() => expect(row(12)).not.toBeNull());
  // An agent fills the field directly, without input events.
  (document.getElementById('queueSearch') as HTMLInputElement).value = 'Case 12';
  const answers = submitFilters(true);
  expect(answers).toHaveLength(1);
  const answer = JSON.parse(await answers[0] as string);
  expect(answer.ok).toBe(true);
  expect(answer.filings.map((f: { id: number }) => f.id)).toEqual([12]);
  expect(vi.mocked(getClerkQueue).mock.lastCall?.[1]).toMatchObject({ search: 'Case 12', page: 1 });
  // Human submissions are never answered as the agent's.
  expect(submitFilters(false)).toEqual([]);
});
