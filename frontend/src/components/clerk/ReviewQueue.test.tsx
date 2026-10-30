import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
      filings: ids.map(summary), total: ids.length, page_size: 25, submitted_count: ids.length, under_review_count: 0,
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

const row = (id: number) => document.getElementById(`queue-filing-${id}`) as HTMLElement;
const reviewButton = (id: number) => within(row(id)).getByRole('button', { name: `Review filing #${id}` });

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
  await waitFor(() => expect(document.activeElement).toBe(reviewButton(13)));
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
  const acceptSelected = screen.getByRole('button', { name: 'Accept 2 filings' });
  acceptSelected.focus();

  fireEvent.click(acceptSelected);

  await waitFor(() => expect(document.activeElement).toBe(reviewButton(13)));
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

  fireEvent.click(screen.getByRole('button', { name: 'Accept 1 filing' }));

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toBe(`${message}Dismiss`);
  await waitFor(() => expect(document.activeElement).toBe(reviewButton(11)));
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

function serveQueuePage(ids: number[], total: number) {
  vi.mocked(getClerkQueue).mockResolvedValue({
    filings: ids.map(summary), total, page_size: 25, submitted_count: total, under_review_count: 0,
    waiting_48h: 0, oldest_submitted_at: null, as_of: '2026-09-28T13:00:00Z',
  });
}

const queueOptions = () => vi.mocked(getClerkQueue).mock.lastCall?.[1];

it('gives each row a named button that opens the review', async () => {
  serveQueues([11, 12]);
  vi.mocked(getFiling).mockResolvedValue(envelope(12));
  openQueue();
  await screen.findByText('Case 12');

  fireEvent.click(reviewButton(12));

  await screen.findByRole('heading', { name: 'Filing #12' });
  expect(getFiling).toHaveBeenCalledTimes(1);
});

it('keeps a click anywhere on the row as a mouse shortcut, without another tab stop', async () => {
  serveQueues([11, 12]);
  openQueue();
  await openReview(12);

  expect(row(12).hasAttribute('tabindex')).toBe(false);
  expect(row(11).hasAttribute('tabindex')).toBe(false);
});

it('labels every row value with its column, so a row still reads when it stacks on a phone', async () => {
  serveQueues([11]);
  openQueue();
  await screen.findByText('Case 11');

  const cells = within(row(11)).getAllByRole('cell');
  expect(cells.map(cell => cell.getAttribute('data-label')))
    .toEqual([null, null, 'Case title', 'Submitted', 'Age', 'Documents', 'Status']);
  expect(screen.getAllByRole('columnheader').map(cell => cell.textContent).slice(2))
    .toEqual(['Case title', 'Submitted', 'Age', 'Documents', 'Status']);
  expect(cells[3].textContent).toMatch(/^Sep 28, 2026, \d{1,2}:00 [AP]M \S+/);
});

it('keeps Select all usable when the column headings are hidden on a phone', async () => {
  serveQueues([11, 12]);
  openQueue();
  await screen.findByText('Case 11');

  const selectAll = screen.getByRole('checkbox', { name: 'Select all filings' });
  expect(selectAll.closest('label')?.textContent).toBe('Select all');
  fireEvent.click(selectAll);

  expect(screen.getByText('2 filings selected')).toBeTruthy();
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select filing 11' }));
  expect(screen.getByText('1 filing selected')).toBeTruthy();
});

it('puts the working court in the heading row, with no count tiles', async () => {
  serveQueues([11]);
  openQueue();
  await screen.findByText('Case 11');

  const heading = screen.getByRole('heading', { level: 1, name: 'Clerk Review Queue' });
  expect(heading.parentElement?.contains(screen.getByLabelText('Working court'))).toBe(true);
  expect(screen.queryByText('Matching filings')).toBeNull();
  expect(screen.queryByText('Waiting 48+ hours')).toBeNull();
});

it('folds the queue counts into one line', async () => {
  serveQueues([11, 12]);
  vi.mocked(getClerkQueue).mockResolvedValue({
    filings: [summary(11)], total: 1, page_size: 25, submitted_count: 1, under_review_count: 0, waiting_48h: 1,
    oldest_submitted_at: '2026-09-28T12:00:00Z', as_of: '2026-09-28T13:00:00Z',
  });
  openQueue();

  const line = await screen.findByText(/matching filing/);
  expect(line.textContent).toMatch(/^1 matching filing · 1 waiting at least 48 hours · Oldest received Sep 28, 2026, \d{1,2}:00 [AP]M \S+$/);
  expect(document.body.textContent).not.toMatch(/Measured:|Ages are elapsed/);
});

it('leaves the oldest receipt out of the line when the queue is empty', async () => {
  serveQueues([]);
  openQueue();

  expect((await screen.findByText(/matching filing/)).textContent).toBe('0 matching filings · 0 waiting at least 48 hours');
});

it('loads the queue for the working court with the default filters', async () => {
  serveQueues([11, 12]);
  openQueue();

  await screen.findByText('Case 12');
  expect(vi.mocked(getClerkQueue).mock.lastCall?.[0]).toBe(3);
  expect(queueOptions()).toMatchObject({ status: 'all', search: '', waiting_48h_only: false, page: 1 });
});

it('applies the submitted status, search and waiting filters', async () => {
  serveQueues([11, 12], [12]);
  openQueue();
  await screen.findByText('Case 11');

  fireEvent.change(screen.getByLabelText('Filter'), { target: { value: 'under_review' } });
  fireEvent.change(screen.getByLabelText('Case title, case number or #filing number'), { target: { value: ' Case 12 ' } });
  fireEvent.click(screen.getByLabelText('Waiting at least 48 hours'));
  fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));

  await waitFor(() => expect(screen.queryByText('Case 11')).toBeNull());
  expect(screen.getByText('Case 12')).toBeTruthy();
  expect(queueOptions()).toMatchObject({ status: 'under_review', search: 'Case 12', waiting_48h_only: true, page: 1 });
  expect(screen.getByRole('button', { name: 'Refresh' })).toBeTruthy();
});

it('loads the queue again when unchanged filters are submitted', async () => {
  serveQueues([11]);
  openQueue();
  await screen.findByText('Case 11');
  expect(getClerkQueue).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

  await waitFor(() => expect(getClerkQueue).toHaveBeenCalledTimes(2));
  expect(queueOptions()).toMatchObject({ status: 'all', search: '', waiting_48h_only: false, page: 1 });
});

it('pages through a queue longer than one page', async () => {
  serveQueuePage([11, 12], 30);
  openQueue();
  await screen.findByText('Case 11');
  expect(screen.getByText('Page 1 of 2')).toBeTruthy();
  expect((screen.getByRole('button', { name: 'Previous' }) as HTMLButtonElement).disabled).toBe(true);

  fireEvent.click(screen.getByRole('button', { name: 'Next' }));

  await screen.findByText('Page 2 of 2');
  expect(queueOptions()).toMatchObject({ page: 2 });
  await waitFor(() => expect((screen.getByRole('button', { name: 'Next' }) as HTMLButtonElement).disabled).toBe(true));

  fireEvent.click(screen.getByRole('button', { name: 'Previous' }));

  await screen.findByText('Page 1 of 2');
  expect(queueOptions()).toMatchObject({ page: 1 });
});

it('counts queue pages with the page size the queue reports', async () => {
  vi.mocked(getClerkQueue).mockResolvedValue({
    filings: [11, 12].map(summary), total: 30, page_size: 10, submitted_count: 30, under_review_count: 0,
    waiting_48h: 0, oldest_submitted_at: null, as_of: '2026-09-28T13:00:00Z',
  });
  openQueue();

  expect(await screen.findByText('Page 1 of 3')).toBeTruthy();
});

it('shows no pagination when the queue fits on one page', async () => {
  serveQueuePage([11, 12], 2);
  openQueue();
  await screen.findByText('Case 11');

  expect(screen.queryByRole('button', { name: 'Next' })).toBeNull();
  expect(screen.queryByText(/^Page \d+ of \d+$/)).toBeNull();
});

it('opens a filing for review and closes the review back to its row', async () => {
  serveQueues([11, 12]);
  openQueue();
  await openReview(12);

  expect(vi.mocked(getFiling).mock.lastCall?.[0]).toBe(12);
  expect(screen.getByRole('heading', { name: 'Review actions' })).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'Close review' }));

  expect(screen.queryByRole('heading', { name: 'Filing #12' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
  expect(document.activeElement).toBe(reviewButton(12));
});

it('requires a reason before a filing can be returned or rejected', async () => {
  serveQueues([11]);
  openQueue();
  await openReview(11);

  const returnButton = screen.getByRole('button', { name: 'Return for Correction' }) as HTMLButtonElement;
  const rejectButton = screen.getByRole('button', { name: 'Reject' }) as HTMLButtonElement;
  expect(returnButton.disabled).toBe(true);
  expect(rejectButton.disabled).toBe(true);
  expect((screen.getByRole('button', { name: 'Accept' }) as HTMLButtonElement).disabled).toBe(false);

  fireEvent.change(screen.getByLabelText('Review reason'), { target: { value: 'Wrong court' } });

  expect(returnButton.disabled).toBe(false);
  expect(rejectButton.disabled).toBe(false);
});

it('sends a typed reason with a return', async () => {
  serveQueues([11], []);
  vi.mocked(reviewFiling).mockResolvedValue(envelope(11));
  openQueue();
  await openReview(11);
  fireEvent.change(screen.getByLabelText('Review reason'), { target: { value: 'Caption is incomplete' } });

  fireEvent.click(screen.getByRole('button', { name: 'Return for Correction' }));

  await waitFor(() => expect(reviewFiling).toHaveBeenCalledTimes(1));
  expect(reviewFiling).toHaveBeenCalledWith(expect.objectContaining({ id: 11, submission_count: 1 }),
    'return', 'Caption is incomplete');
});

it('does not reject a filing when the clerk cancels the confirmation', async () => {
  serveQueues([11]);
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  openQueue();
  await openReview(11);
  fireEvent.change(screen.getByLabelText('Review reason'), { target: { value: 'Wrong court' } });

  fireEvent.click(screen.getByRole('button', { name: 'Reject' }));

  expect(confirm).toHaveBeenCalledTimes(1);
  expect(reviewFiling).not.toHaveBeenCalled();
  expect(screen.getByRole('heading', { name: 'Filing #11' })).toBeTruthy();
  confirm.mockRestore();
});

it('shows a failed queue load inline and loads it again on retry', async () => {
  vi.mocked(getClerkQueue).mockRejectedValueOnce(new Error('Network Error'));
  openQueue();

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain("We couldn't load the review queue. Please retry.");
  expect(screen.queryByText('No filings match these filters in this court.')).toBeNull();
  serveQueues([11]);

  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

  await screen.findByText('Case 11');
  expect(screen.queryByRole('alert')).toBeNull();
});

it('shows a filing that fails to open inline in the review panel', async () => {
  serveQueues([11]);
  vi.mocked(getFiling).mockRejectedValueOnce({ response: { status: 404, data: { detail: 'Filing not found' } } })
    .mockResolvedValueOnce(envelope(11));
  openQueue();
  fireEvent.click(await screen.findByText('Case 11'));

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Filing not found');
  expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

  await screen.findByRole('button', { name: 'Accept' });
  expect(vi.mocked(getFiling).mock.calls.map(([id]) => id)).toEqual([11, 11]);
});
