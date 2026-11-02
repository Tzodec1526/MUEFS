import { cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useFilingDraft } from './useFilingDraft';

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

it('reports a recovery copy as available on a fresh store while saving is paused', () => {
  const { result } = renderHook(() => useFilingDraft(1, new URLSearchParams('court_id=3'), {
    loadedFiling: null, submission: undefined, paused: true,
  }));

  expect(result.current.dirty).toBe(true);
  expect(sessionStorage.length).toBe(0);
  expect(result.current.recoveryAvailable).toBe(true);
});
