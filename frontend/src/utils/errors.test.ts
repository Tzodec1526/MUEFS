import { describe, expect, it } from 'vitest';
import { errorMessage, getBlobErrorDetail, getErrorDetail, loadFailure } from './errors';

describe('API error messages', () => {
  it('preserves the server explanation for a rejected action', () => {
    expect(getErrorDetail({ response: { data: { detail: 'The payment record changed.' } } }))
      .toBe('The payment record changed.');
  });
  it('renders validation messages without returning objects or echoing submitted data', () => {
    expect(getErrorDetail({ response: { data: { detail: [
      { msg: 'Receipt number is required', input: 'private input' },
      { msg: 'Receipt time must include a time zone' },
    ] } } })).toBe('Receipt number is required Receipt time must include a time zone');
  });
  it('lets callers use their fallback when a response has no readable explanation', () => {
    for (const error of [null, new Error('Network failure'), { response: { data: { detail: [{}] } } }]) {
      expect(getErrorDetail(error)).toBeUndefined();
    }
  });
  it('reads the explanation from a failed file download', async () => {
    const body = new Blob([JSON.stringify({ detail: 'Document failed its retained integrity check' })]);
    expect(await getBlobErrorDetail({ response: { data: body } }))
      .toBe('Document failed its retained integrity check');
    expect(await getBlobErrorDetail({ response: { data: new Blob(['<html>']) } })).toBeUndefined();
  });

  it('prefers the server explanation, then the status, then the caller fallback', () => {
    expect(errorMessage({ response: { status: 409, data: { detail: 'The filing changed.' } } }, 'Could not save.'))
      .toBe('The filing changed.');
    expect(errorMessage({ response: { status: 429 } }, 'Could not save.'))
      .toBe('Too many requests. Please wait a moment and try again.');
    expect(errorMessage({ response: { status: 403, data: {} } }, 'Could not save.'))
      .toBe('You do not have permission to do that.');
    expect(errorMessage({ response: { status: 500 } }, 'Could not save.')).toBe('Could not save.');
    expect(errorMessage(new Error('Network Error'), 'Could not save.')).toBe('Could not save.');
  });
  it('offers a retry for a failed load unless the account is not signed in or not allowed', () => {
    expect(loadFailure({ response: { status: 403, data: { detail: 'Court staff access is required.' } } }, 'Could not load.'))
      .toEqual({ message: 'Court staff access is required.', retry: false });
    expect(loadFailure({ response: { status: 401, data: { detail: 'Authentication required' } } }, 'Could not load.'))
      .toEqual({ message: 'Authentication required', retry: false });
    expect(loadFailure({ response: { status: 429 } }, 'Could not load.'))
      .toEqual({ message: 'Too many requests. Please wait a moment and try again.', retry: true });
    expect(loadFailure({ response: { status: 503 } }, 'Could not load.')).toEqual({ message: 'Could not load.', retry: true });
    expect(loadFailure(new Error('Network Error'), 'Could not load.')).toEqual({ message: 'Could not load.', retry: true });
  });
});
