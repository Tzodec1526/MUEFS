import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { listFilings, type FilingSummary } from '../../api/filings';
import MyFilings from './MyFilings';

vi.mock('../../api/filings', () => ({ listFilings: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function filing(id: number, overrides: Partial<FilingSummary> = {}): FilingSummary {
  return {
    id, court_id: 3, case_id: null, filer_id: 1, status: 'draft', case_title: `Case ${id}`, filing_description: null,
    submitted_at: null, rejection_reason: null, fee_waiver_requested: false, fee_waiver_granted: null,
    created_at: '2026-09-28T12:00:00Z', updated_at: '2026-09-28T12:00:00Z', submission_count: 0, document_count: 1,
    ...overrides,
  };
}

const counts = { draft: 2, submitted: 1, under_review: 0, accepted: 3, rejected: 0, returned: 1, served: 0 };

function serve(filings: FilingSummary[], total = filings.length, status_counts: Record<string, number> = counts) {
  vi.mocked(listFilings).mockResolvedValue({ filings, total, status_counts, court_names: { 3: 'Third Circuit Court' } });
}

function open(entry = '/filings') {
  return render(<MemoryRouter initialEntries={[entry]}><MyFilings /></MemoryRouter>);
}

const filter = () => screen.getByLabelText('Filter by status') as HTMLSelectElement;
const options = () => within(filter()).getAllByRole('option').map(option => option.textContent);

it('offers one status filter with the count of every status, including empty ones', async () => {
  serve([filing(1)]);
  open();

  await screen.findByText('Case 1');
  expect(options()).toEqual([
    'All statuses (7)', 'Draft (2)', 'Submitted (1)', 'Under review (0)', 'Accepted (3)', 'Rejected (0)',
    'Returned (1)', 'Service documents recorded (0)',
  ]);
});

it('keeps counts out of the filter until they have loaded', async () => {
  vi.mocked(listFilings).mockReturnValue(new Promise(() => {}));
  open();

  expect(options().slice(0, 2)).toEqual(['All statuses', 'Draft']);
  expect(await screen.findByText('Loading filings...')).toBeTruthy();
});

it('treats a status the server left out of its counts as zero', async () => {
  serve([filing(1)], 1, { draft: 1 });
  open();

  await screen.findByText('Case 1');
  expect(options().slice(0, 3)).toEqual(['All statuses (1)', 'Draft (1)', 'Submitted (0)']);
});

it('has no status tiles beside the filter', async () => {
  serve([filing(1)]);
  open();

  await screen.findByText('Case 1');
  expect(screen.getAllByRole('button').map(button => button.textContent)).toEqual(['Continue Filing', 'View Filing']);
});

it('asks for the status chosen in the filter', async () => {
  serve([filing(1)]);
  open();
  await screen.findByText('Case 1');

  fireEvent.change(filter(), { target: { value: 'accepted' } });

  await vi.waitFor(() => expect(vi.mocked(listFilings).mock.lastCall?.[0]).toMatchObject({ status: 'accepted', page: 1 }));
  expect(filter().value).toBe('accepted');
});

it('counts filings and documents in real plurals', async () => {
  serve([filing(1, { document_count: 1 }), filing(2, { document_count: 3 })]);
  open();

  expect(await screen.findByText('2 filings')).toBeTruthy();
  expect(screen.getByText('1 document')).toBeTruthy();
  expect(screen.getByText('3 documents')).toBeTruthy();
});

it('counts one filing in the singular', async () => {
  serve([filing(1, { document_count: 0 })]);
  open();

  expect(await screen.findByText('1 filing')).toBeTruthy();
  expect(screen.getByText('0 documents')).toBeTruthy();
});

it('shows no filing count when the list failed to load', async () => {
  vi.mocked(listFilings).mockRejectedValue(new Error('Network Error'));
  open();

  await screen.findByRole('alert');
  expect(screen.queryByText('0 filings')).toBeNull();
});

it('makes Resubmit the primary action on a returned filing', async () => {
  serve([filing(1, { status: 'returned', rejection_reason: 'Missing summons' })]);
  open();

  const resubmit = await screen.findByRole('button', { name: 'Resubmit' });
  expect(resubmit.className).toContain('btn-primary');
  expect(resubmit.className).not.toContain('btn-warning');
});

it('shows the time of a filing in the one date-time format', async () => {
  serve([filing(1, { submitted_at: '2026-09-28T12:00:00Z', status: 'submitted' })]);
  open();

  expect(await screen.findByText(/^Sep 28, 2026, \d{1,2}:00 [AP]M \S+$/)).toBeTruthy();
});

it('steps from the page heading straight to one heading per filing', async () => {
  serve([filing(1)]);
  open();

  await screen.findByText('Case 1');
  expect(screen.getAllByRole('heading').map(heading => heading.tagName)).toEqual(['H1', 'H2']);
});
