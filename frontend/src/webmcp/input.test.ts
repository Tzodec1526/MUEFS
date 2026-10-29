import { describe, expect, it } from 'vitest';
import { TOOL_DEFINITIONS } from './definitions';
import { checkToolInput } from './input';

const schemaOf = (name: string) => TOOL_DEFINITIONS.find(tool => tool.name === name)!.inputSchema;

describe('checkToolInput', () => {
  it('accepts input within the schema and drops nulls standing for omitted values', () => {
    expect(checkToolInput(schemaOf('search_cases'), { party_name: 'Smith', court_id: null, page: 2 }))
      .toEqual({ ok: true, input: { party_name: 'Smith', page: 2 } });
    expect(checkToolInput(schemaOf('get_agent_catalog'), undefined)).toEqual({ ok: true, input: {} });
  });

  it('passes through properties the schema does not name', () => {
    expect(checkToolInput(schemaOf('navigate_to'), { path: '/cases/search', confirmed: true }))
      .toEqual({ ok: true, input: { path: '/cases/search', confirmed: true } });
  });

  it.each([
    [{ case_id: 0 }, 'case_id must be from 1 to 2147483647.'],
    [{ case_id: 2_147_483_648 }, 'case_id must be from 1 to 2147483647.'],
    [{ case_id: '12' }, 'case_id must be an integer.'],
    [{ case_id: Number.NaN }, 'case_id must be an integer.'],
    [{}, 'case_id is required.'],
    [{ case_id: null }, 'case_id is required.'],
  ])('rejects docket input %j', (input, error) => {
    expect(checkToolInput(schemaOf('get_case_docket'), input)).toEqual({ ok: false, error });
  });

  it('checks enums, lengths and booleans', () => {
    const queue = schemaOf('get_clerk_review_queue');
    expect(checkToolInput(queue, { status: 'waivers' }))
      .toEqual({ ok: false, error: 'status must be one of: all, submitted, under_review.' });
    expect(checkToolInput(queue, { search: 'x'.repeat(201) }))
      .toEqual({ ok: false, error: 'search must be at most 200 characters.' });
    expect(checkToolInput(queue, { waiting_48h_only: 'true' }))
      .toEqual({ ok: false, error: 'waiting_48h_only must be true or false.' });
  });

  it.each([['a string', 'case_id=12'], ['an array', [12]]])('rejects input that is %s', (_what, input) => {
    expect(checkToolInput(schemaOf('get_case_docket'), input)).toEqual({ ok: false, error: 'Tool input must be a JSON object.' });
  });

  it('does not take a required value from a "__proto__" key', () => {
    const input = JSON.parse('{"__proto__": {"case_id": 12}}');
    expect(checkToolInput(schemaOf('get_case_docket'), input)).toEqual({ ok: false, error: 'case_id is required.' });
  });
});
