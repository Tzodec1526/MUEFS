import { CanceledError } from 'axios';
import { expect, it } from 'vitest';
import { needsErrorMessage } from './client';

it('asks callers to explain only the failures the client did not already show', () => {
  expect(needsErrorMessage(new Error('Network Error'))).toBe(true);
  expect(needsErrorMessage({ response: { status: 409, data: { detail: 'Court already in favorites' } } }))
    .toBe(false);
  expect(needsErrorMessage({ response: { status: 429 } })).toBe(false);
  expect(needsErrorMessage({ response: { status: 403 } })).toBe(false);
  // Expired sessions redirect without a toast, so the caller still owns the message.
  expect(needsErrorMessage({ response: { status: 401, data: { detail: 'Authentication required' } } }))
    .toBe(true);
  expect(needsErrorMessage(new CanceledError('The signed-in account changed.'))).toBe(false);
});
