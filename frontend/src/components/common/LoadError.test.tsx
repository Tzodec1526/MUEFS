import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import LoadError from './LoadError';

afterEach(cleanup);

it('offers a retry for a failure that a second try may fix', () => {
  const retry = vi.fn();
  render(<LoadError failure={{ message: 'Could not load accounts.', retry: true }} onRetry={retry} />);

  expect(screen.getByRole('alert').textContent).toContain('Could not load accounts.');
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(retry).toHaveBeenCalledTimes(1);
});

it('offers no retry when the account is not signed in or not allowed', () => {
  render(<LoadError failure={{ message: 'System administrator access is required.', retry: false }} onRetry={vi.fn()} />);

  expect(screen.getByRole('alert').textContent).toContain('System administrator access is required.');
  expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
});
