import { describe, expect, it } from 'vitest';
import { formatCourtDate, formatDateTime, formatShortDate, plural } from './format';

describe('formatDateTime', () => {
  it.each([
    ['a Z suffix', '2026-08-14T21:39:00Z'],
    ['a +00:00 offset', '2026-08-14T21:39:00+00:00'],
    ['no offset, which the server means as UTC', '2026-08-14T21:39:00'],
    ['fractional seconds and no offset', '2026-08-14T21:39:00.123456'],
    ['the same instant in another offset', '2026-08-14T17:39:00-04:00'],
  ])('reads a timestamp with %s as the same instant', (_kind, value) => {
    expect(formatDateTime(value, 'UTC')).toBe('Aug 14, 2026, 9:39 PM UTC');
  });

  it("shows the instant in the court's time zone, naming the zone", () => {
    expect(formatDateTime('2026-08-14T21:39:00Z', 'America/Detroit')).toBe('Aug 14, 2026, 5:39 PM EDT');
    expect(formatDateTime('2026-01-14T21:39:00Z', 'America/Detroit')).toBe('Jan 14, 2026, 4:39 PM EST');
  });

  it("crosses midnight with the time zone, unlike a court's civil date", () => {
    expect(formatDateTime('2026-08-15T02:00:00Z', 'America/Detroit')).toBe('Aug 14, 2026, 10:00 PM EDT');
  });

  it("uses the viewer's time zone unless told otherwise, whatever suffix the server sent", () => {
    const viewer = formatDateTime('2026-08-14T21:39:00Z');
    expect(viewer).toMatch(/^Aug 1[45], 2026, \d{1,2}:39 [AP]M \S+/);
    expect(formatDateTime('2026-08-14T21:39:00')).toBe(viewer);
    expect(formatDateTime('2026-08-14T21:39:00+00:00')).toBe(viewer);
  });

  it('says so when no time was recorded', () => {
    expect(formatDateTime(null)).toBe('Not recorded');
  });
});

describe('legal dates', () => {
  it('keeps a court date on its civil day whatever the time zone', () => {
    expect(formatCourtDate('2026-03-02')).toBe('Mar 2, 2026');
    expect(formatCourtDate('2026-12-31')).toBe('Dec 31, 2026');
  });

  it('says so when the court has not set one', () => {
    expect(formatCourtDate(null)).toBe('Not established');
  });
});

it('shows a timestamp as a short date', () => {
  expect(formatShortDate('2026-08-14T12:00:00Z')).toBe('Aug 14, 2026');
});

describe('plural', () => {
  it.each([
    [0, '0 filings'],
    [1, '1 filing'],
    [2, '2 filings'],
  ])('counts %i', (count, text) => {
    expect(plural(count, 'filing')).toBe(text);
  });

  it('takes an irregular plural', () => {
    expect(plural(2, 'entry', 'entries')).toBe('2 entries');
    expect(plural(1, 'entry', 'entries')).toBe('1 entry');
  });
});

it('leaves one date-time format in the app', () => {
  const sources = import.meta.glob<string>(['../**/*.{ts,tsx}', '!../**/*.test.{ts,tsx}', '!./format.ts'],
    { query: '?raw', import: 'default', eager: true });
  const copies = Object.entries(sources)
    .filter(([, source]) => /\.toLocaleString\(|\.toLocaleDateString\(|\.toISOString\(\)\.replace/.test(source))
    .map(([path]) => path);
  expect(Object.keys(sources).length).toBeGreaterThan(50);
  expect(copies).toEqual([]);
});
