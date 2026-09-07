import { describe, expect, it } from 'vitest';
import { getErrorDetail } from './errors';

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
});
