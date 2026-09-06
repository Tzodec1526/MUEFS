import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearFilingDraft, filingDraftKey, loadFilingDraft, loadLegacyFilingDraft, saveFilingDraft,
  type FilingDraft,
} from './filingDraft';

const draft: FilingDraft = {
  courtId: 1, courtName: 'Test court', caseId: null, filingType: 'initial',
  caseTypeId: 1, caseTypeName: 'Civil', caseTitle: 'Unsaved title', filingDescription: 'Private edits',
  filingId: 7, detailsToken: 'a'.repeat(64), caseChoiceMade: true, motionSubtype: null,
};

beforeEach(() => {
  for (const name of ['sessionStorage', 'localStorage']) {
    const values = new Map<string, string>();
    vi.stubGlobal(name, {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
  }
});
afterEach(() => vi.unstubAllGlobals());

describe('unsaved filing recovery', () => {
  it('keeps separate account/filing edits and excludes document and payment state', () => {
    const first = filingDraftKey(1, '7'), second = filingDraftKey(1, '8');
    const otherAccount = filingDraftKey(2, '7');
    saveFilingDraft(first, { ...draft, documents: [{ title: 'Private attachment' }], paymentComplete: true } as FilingDraft);
    saveFilingDraft(second, { ...draft, filingId: 8, caseTitle: 'Second filing' });
    expect(loadFilingDraft(first)?.caseTitle).toBe('Unsaved title');
    expect(loadFilingDraft(second)?.caseTitle).toBe('Second filing');
    expect(loadFilingDraft(otherAccount)).toBeNull();
    expect(sessionStorage.getItem(first)).not.toContain('Private attachment');
    expect(sessionStorage.getItem(first)).not.toContain('paymentComplete');
    clearFilingDraft(first);
    expect(loadFilingDraft(first)).toBeNull();
    expect(loadFilingDraft(second)?.caseTitle).toBe('Second filing');
  });

  it('rejects malformed recovery instead of passing it into the wizard', () => {
    const key = filingDraftKey(1, '7');
    for (const damaged of ['{', 'null', '[]', JSON.stringify({ ...draft, courtId: true }),
      JSON.stringify({ ...draft, detailsToken: ['a'.repeat(64)] }),
      JSON.stringify({ ...draft, creationKey: 7 }), JSON.stringify({ ...draft, creationKey: 'broken' }),
      JSON.stringify({ ...draft, filingDescription: { private: 'value' } })]) {
      sessionStorage.setItem(key, damaged);
      expect(loadFilingDraft(key)).toBeNull();
    }
  });

  it('retains the same creation attempt across recovery without invalidating older drafts', () => {
    const key = filingDraftKey(1, 'new:');
    saveFilingDraft(key, draft);
    expect(loadFilingDraft(key)?.creationKey).toBeUndefined();
    const creationKey = '12345678-1234-1234-1234-123456789012';
    saveFilingDraft(key, { ...draft, filingId: null, creationKey });
    const recovered = loadFilingDraft(key)!;
    saveFilingDraft(key, { ...recovered, caseTitle: 'Edited after a lost response' });
    expect(loadFilingDraft(key)?.creationKey).toBe(creationKey);
  });

  it('reports unavailable storage without throwing away the form values', () => {
    vi.stubGlobal('sessionStorage', {
      getItem: () => { throw new Error('Storage denied'); },
      setItem: () => { throw new Error('Quota exceeded'); },
      removeItem: () => { throw new Error('Storage denied'); },
    });
    expect(saveFilingDraft('key', draft)).toBe(false);
    expect(loadFilingDraft('key')).toBeNull();
    expect(() => clearFilingDraft('key')).not.toThrow();
    expect(draft.caseTitle).toBe('Unsaved title');
  });

  it('offers legacy edits only for a server-verified owned filing, with an unknown base', () => {
    localStorage.setItem('muefs_filing_draft', JSON.stringify(draft));
    expect(loadLegacyFilingDraft(2, { id: 7, filer_id: 1 })).toBeNull();
    expect(loadLegacyFilingDraft(1, { id: 8, filer_id: 1 })).toBeNull();
    expect(loadLegacyFilingDraft(1, { id: 7, filer_id: 1 })).toMatchObject({
      caseTitle: 'Unsaved title', detailsToken: null,
    });
    clearFilingDraft('key', 8);
    expect(localStorage.getItem('muefs_filing_draft')).not.toBeNull();
    clearFilingDraft('key', 7);
    expect(localStorage.getItem('muefs_filing_draft')).toBeNull();
  });
});
