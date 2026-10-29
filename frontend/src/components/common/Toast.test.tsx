// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { emitToast } from '../../utils/toastBus';
import { ToastProvider } from './Toast';

afterEach(cleanup);

function visibleToasts() {
  return screen.queryAllByRole('status').map(toast => toast.querySelector('span')?.textContent);
}

it('shows a repeated message once, and treats a different tone as a different toast', () => {
  render(<ToastProvider><main /></ToastProvider>);
  act(() => emitToast('Could not save the filing.', 'error'));
  act(() => {
    emitToast('Could not save the filing.', 'error');
    emitToast('Could not save the filing.', 'error');
  });
  expect(visibleToasts()).toEqual(['Could not save the filing.']);

  act(() => emitToast('Could not save the filing.', 'info'));
  expect(visibleToasts()).toEqual(['Could not save the filing.', 'Could not save the filing.']);
});

it('keeps only the three newest toasts on screen', () => {
  render(<ToastProvider><main /></ToastProvider>);
  for (const message of ['First', 'Second', 'Third', 'Fourth']) act(() => emitToast(message));
  expect(visibleToasts()).toEqual(['Second', 'Third', 'Fourth']);
});
