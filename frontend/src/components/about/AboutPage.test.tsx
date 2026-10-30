import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { getPublicStats, type PublicPlatformStats } from '../../api/public';
import AboutPage from './AboutPage';

vi.mock('../../api/public', () => ({ getPublicStats: vi.fn() }));

const stats = {
  courts_efiling_enabled: 255, public_cases_indexed: 40, total_filings: 12, pending_clerk_review: 3,
  mcr_document_types: 45, max_upload_mb: 50, mifile_max_upload_mb: 30, cms_integration: 'stub',
} as PublicPlatformStats;

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const open = () => render(<MemoryRouter><AboutPage /></MemoryRouter>);
const uploadRow = () => within(screen.getByRole('row', { name: /Upload limit/ })).getAllByRole('cell')
  .map(cell => cell.textContent);

it('gives the comparison the same upload limits as the statistics', async () => {
  vi.mocked(getPublicStats).mockResolvedValue(stats);
  open();

  await screen.findByText('Max upload');
  expect(uploadRow()).toEqual(['30 MB', '50 MB']);
  expect(screen.getByText('Max upload').previousElementSibling?.textContent).toBe('50 MB');
  expect(screen.getByText('MiFILE caps at 30 MB')).toBeTruthy();
  expect(document.body.textContent).not.toContain('100 MB');
  expect(getPublicStats).toHaveBeenCalledTimes(1);
});

it('states no upload limit while the statistics load', () => {
  vi.mocked(getPublicStats).mockReturnValue(new Promise(() => {}));
  open();

  expect(uploadRow().join(' ')).not.toMatch(/\d/);
});

it('states no upload limit when the statistics failed, and fills it in after a retry', async () => {
  vi.mocked(getPublicStats).mockRejectedValueOnce(new Error('Network Error')).mockResolvedValue(stats);
  open();

  const alert = await screen.findByRole('alert');
  expect(uploadRow().join(' ')).not.toMatch(/\d/);

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  await screen.findByText('Max upload');
  expect(uploadRow()).toEqual(['30 MB', '50 MB']);
});
