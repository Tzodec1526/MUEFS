import { describe, expect, it } from 'vitest';
import { toolsForRole } from './catalog';

describe('toolsForRole', () => {
  it('keeps validate_filing off the public and clerk sets', () => {
    expect(toolsForRole(null).has('validate_filing')).toBe(false);
    expect(toolsForRole('public').has('validate_filing')).toBe(false);
    expect(toolsForRole('clerk').has('validate_filing')).toBe(false);
  });

  it('gives filers validate_filing and start_motion_filing', () => {
    expect(toolsForRole('attorney').has('validate_filing')).toBe(true);
    expect(toolsForRole('srl').has('start_motion_filing')).toBe(true);
    expect(toolsForRole('attorney').has('get_clerk_review_queue')).toBe(false);
  });

  it('gives clerks queue tools including open_filing_for_review', () => {
    expect(toolsForRole('clerk').has('get_clerk_review_queue')).toBe(true);
    expect(toolsForRole('clerk').has('open_filing_for_review')).toBe(true);
    expect(toolsForRole('clerk').has('list_my_filings')).toBe(false);
  });
});
