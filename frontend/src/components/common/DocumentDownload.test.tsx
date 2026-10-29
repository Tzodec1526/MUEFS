import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { apiClient } from '../../api/client';
import DocumentDownload from './DocumentDownload';

vi.mock('../../api/client', () => ({ apiClient: { get: vi.fn() } }));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

/** A failed `responseType: 'blob'` request: axios delivers the error body as a Blob. */
function failWith(status: number, body: Blob) {
  vi.mocked(apiClient.get).mockRejectedValue({ response: { status, data: body } });
}

it('shows the explanation from the error body of a failed download', async () => {
  failWith(409, new Blob([JSON.stringify({ detail: 'Document failed its retained integrity check' })],
    { type: 'application/json' }));
  render(<DocumentDownload id={5} title="Complaint.pdf" />);

  fireEvent.click(screen.getByRole('button', { name: 'Download Complaint.pdf' }));

  expect((await screen.findByRole('alert')).textContent).toBe('Document failed its retained integrity check');
  expect(apiClient.get).toHaveBeenCalledWith('/documents/5/download', { responseType: 'blob' });
});

it('falls back to a retry message when the error body carries no explanation', async () => {
  failWith(502, new Blob(['<html>Bad gateway</html>'], { type: 'text/html' }));
  render(<DocumentDownload id={5} title="Complaint.pdf" />);

  fireEvent.click(screen.getByRole('button', { name: 'Download Complaint.pdf' }));

  expect((await screen.findByRole('alert')).textContent).toBe('Download unavailable. Please retry.');
});
