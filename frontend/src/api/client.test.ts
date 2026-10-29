import { AxiosError, CanceledError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, expect, it, vi } from 'vitest';
import { onToast } from '../utils/toastBus';
import { actionErrorMessage, apiClient } from './client';

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

function failWith(status: number, data: unknown) {
  return async (config: InternalAxiosRequestConfig) => {
    throw new AxiosError(`Request failed with status code ${status}`, 'ERR_BAD_REQUEST', config, undefined,
      { status, data, statusText: '', headers: {}, config } as AxiosResponse);
  };
}

it.each([
  [403, { detail: 'System administrator access is required.' }],
  [409, { detail: 'Court already in favorites' }],
  [429, {}],
  [403, {}],
  [500, { detail: 'Internal error' }],
])('leaves a failed request with status %i for the caller to explain, without a toast', async (status, data) => {
  const toasts = vi.fn();
  const stop = onToast(toasts);
  try {
    const request = apiClient.get('/admin/access', { adapter: failWith(status, data) });
    await expect(request).rejects.toMatchObject({ response: { status, data } });
  } finally { stop(); }
  expect(toasts).not.toHaveBeenCalled();
});

it('gives a background action the message to show, and none for a cancelled request', () => {
  expect(actionErrorMessage({ response: { status: 409, data: { detail: 'Court already in favorites' } } }, 'Could not update favorite'))
    .toBe('Court already in favorites');
  expect(actionErrorMessage({ response: { status: 429 } }, 'Could not update favorite'))
    .toBe('Too many requests. Please wait a moment and try again.');
  expect(actionErrorMessage({ response: { status: 403 } }, 'Could not update favorite'))
    .toBe('You do not have permission to do that.');
  expect(actionErrorMessage(new Error('Network Error'), 'Could not update favorite')).toBe('Could not update favorite');
  expect(actionErrorMessage(new CanceledError('The signed-in account changed.'), 'Could not update favorite')).toBeNull();
});
