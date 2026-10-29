import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { searchCases } from '../api/cases';
import AgentDeclarativeSearch from '../components/agent/AgentDeclarativeSearch';
import { ToastProvider } from '../components/common/Toast';
import CaseSearch from '../components/search/CaseSearch';
import { clearAgentActivity, getAgentActivity } from './activity';
import { TOOL_DEFINITIONS } from './definitions';
import { searchTools } from './tools/search';

vi.mock('../api/cases', () => ({ searchCases: vi.fn() }));
vi.mock('../api/courts', () => ({ listCourtDirectory: vi.fn(async () => []) }));
vi.mock('../api/favorites', () => ({ listFavorites: vi.fn(), addFavorite: vi.fn(), removeFavorite: vi.fn() }));
vi.mock('../api/client', () => ({ needsErrorMessage: () => true }));
vi.mock('../components/auth/LoginScreen', () => ({ getDemoRole: () => null }));

type SearchResult = Awaited<ReturnType<typeof searchCases>>;
const NO_CASES: SearchResult = { cases: [], total: 0, page: 1, page_size: 25 };
const THREE_PAGES: SearchResult = {
  total: 60, page: 1, page_size: 25,
  cases: [{ id: 1, case_number: '2026-000001-CZ', title: 'Smith v Jones', status: 'open', court_id: 3,
    court_name: 'Court', court_county: 'Wayne', case_type_id: 7, filed_date: '2026-09-01T12:00:00Z',
    filing_date: null, participants: [{ party_name: 'Jones', role: 'defendant' }] }],
};

// Every search waits until the test settles it.
let unsettled: { resolve: (result: SearchResult) => void; reject: (error: unknown) => void }[] = [];

beforeEach(() => {
  unsettled = [];
  vi.mocked(searchCases).mockImplementation(() => new Promise((resolve, reject) => {
    unsettled.push({ resolve, reject });
  }));
});

afterEach(() => {
  cleanup();
  clearAgentActivity();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

function renderAt(ui: ReactNode, path: string) {
  render(<MemoryRouter initialEntries={[path]}><ToastProvider>{ui}</ToastProvider></MemoryRouter>);
  return document.querySelector<HTMLFormElement>('form[toolname="search_cases_form"]')!;
}

/**
 * Submit the form as a human, or as an agent through the WebMCP declarative API:
 * SubmitEvent.agentInvoked marks the submission, and respondWith() (when the browser has it)
 * takes the answer.
 */
function submit(form: HTMLFormElement, agentInvoked: boolean, respondWith?: (response: Promise<unknown>) => void) {
  const event = new Event('submit', { bubbles: true, cancelable: true });
  if (agentInvoked) Object.defineProperty(event, 'agentInvoked', { value: true });
  if (respondWith) Object.defineProperty(event, 'respondWith', { value: respondWith });
  act(() => { form.dispatchEvent(event); });
}

/** A respondWith() stand-in that keeps what the page passed it. */
function respondWithSpy() {
  const answers: Promise<unknown>[] = [];
  const respondWith = vi.fn((response: Promise<unknown>) => { answers.push(response); });
  return { respondWith, answer: async () => JSON.parse(await answers[0] as string) };
}

async function settleSearches({ afterMs = 0, result = NO_CASES } = {}) {
  if (afterMs) await new Promise(resolve => setTimeout(resolve, afterMs));
  await act(async () => { unsettled.splice(0).forEach(({ resolve }) => resolve(result)); });
}

async function failSearches(error: unknown = new Error('network')) {
  await act(async () => { unsettled.splice(0).forEach(({ reject }) => reject(error)); });
}

/** What the imperative search_cases tool returns when the API answers `result`. */
async function imperativeResult(input: Record<string, unknown>, result: SearchResult) {
  vi.mocked(searchCases).mockResolvedValueOnce(result);
  return await searchTools.search_cases(input) as string;
}

describe('case search form', () => {
  it('logs only agent submissions, timed until the search they started settles', async () => {
    const form = renderAt(<CaseSearch />, '/cases/search');
    await settleSearches();
    const party = screen.getByLabelText('Party Name');

    fireEvent.change(party, { target: { value: 'Smith' } });
    submit(form, false);
    await settleSearches();
    expect(searchCases).toHaveBeenLastCalledWith(expect.objectContaining({ party_name: 'Smith' }), expect.anything());
    expect(getAgentActivity()).toEqual([]);

    fireEvent.change(party, { target: { value: 'Jones' } });
    submit(form, true);
    expect(searchCases).toHaveBeenLastCalledWith(expect.objectContaining({ party_name: 'Jones' }), expect.anything());
    expect(getAgentActivity()).toEqual([]);
    await settleSearches({ afterMs: 30 });

    const [entry, ...rest] = getAgentActivity();
    expect(rest).toEqual([]);
    expect(entry).toMatchObject({ tool: 'search_cases_form', ok: true });
    expect(entry.summary).toContain('party_name=Jones');
    expect(entry.durationMs).toBeGreaterThanOrEqual(25);
  });

  it('logs an agent resubmitting the search already shown', async () => {
    const form = renderAt(<CaseSearch />, '/cases/search?party=Smith');
    await settleSearches();
    submit(form, true);
    expect(searchCases).toHaveBeenCalledTimes(2);
    await settleSearches();
    expect(getAgentActivity()).toEqual([expect.objectContaining({ tool: 'search_cases_form', ok: true })]);
  });

  it.each(['/cases/search?party=Smith&page=1', '/cases/search?party=Smith&case=2026'])(
    'starts one search for an agent resubmitting %s, and credits it no other', async path => {
      // Submitting drops page=1 or reorders the parameters: a new URL, but the same search.
      const form = renderAt(<CaseSearch />, path);
      await settleSearches({ result: THREE_PAGES });
      submit(form, true);
      expect(searchCases).toHaveBeenCalledTimes(2);
      await settleSearches({ result: THREE_PAGES });
      expect(searchCases).toHaveBeenCalledTimes(2);
      expect(getAgentActivity()).toEqual([expect.objectContaining({ tool: 'search_cases_form', ok: true })]);

      act(() => { fireEvent.click(screen.getByRole('button', { name: 'Next' })); });
      expect(searchCases).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }), expect.anything());
      await settleSearches({ result: THREE_PAGES });
      expect(getAgentActivity()).toHaveLength(1);
    },
  );

  it('never logs a human Retry as the search of an earlier agent submission', async () => {
    // docs/WEBMCP.md: human searches never enter the feed.
    const form = renderAt(<CaseSearch />, '/cases/search?party=Smith&page=1');
    await failSearches();

    submit(form, true);
    expect(searchCases).toHaveBeenCalledTimes(2);
    await failSearches();
    expect(getAgentActivity()).toEqual([expect.objectContaining({ tool: 'search_cases_form', ok: false })]);

    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Retry' })); });
    expect(searchCases).toHaveBeenCalledTimes(3);
    await settleSearches();
    expect(getAgentActivity()).toEqual([expect.objectContaining({ tool: 'search_cases_form', ok: false })]);
  });

  it('answers and logs as cancelled an agent search that a human search replaced', async () => {
    const form = renderAt(<CaseSearch />, '/cases/search');
    await settleSearches();
    const party = screen.getByLabelText('Party Name');
    const agent = respondWithSpy();

    fireEvent.change(party, { target: { value: 'Jones' } });
    submit(form, true, agent.respondWith);
    fireEvent.change(party, { target: { value: 'Smith' } });
    submit(form, false);
    expect(searchCases).toHaveBeenCalledTimes(3);
    await settleSearches();

    // The human's search is never credited to the agent.
    const [entry, ...rest] = getAgentActivity();
    expect(rest).toEqual([]);
    expect(entry).toMatchObject({ tool: 'search_cases_form', ok: false });
    expect(entry.summary).toContain('party_name=Jones');
    expect(await agent.answer()).toMatchObject({ ok: false, code: 'cancelled' });
  });

  it('answers the agent through respondWith with what the imperative search_cases tool returns', async () => {
    const form = renderAt(<CaseSearch />, '/cases/search');
    await settleSearches();
    fireEvent.change(screen.getByLabelText('Party Name'), { target: { value: 'Jones' } });
    const agent = respondWithSpy();

    submit(form, true, agent.respondWith);
    // During dispatch, after preventDefault, as the explainer requires.
    expect(agent.respondWith).toHaveBeenCalledOnce();
    expect(agent.respondWith.mock.calls[0][0]).toBeInstanceOf(Promise);
    await settleSearches({ result: THREE_PAGES });

    const answer = await agent.respondWith.mock.calls[0][0];
    expect(answer).toBe(await imperativeResult({ party_name: 'Jones' }, THREE_PAGES));
    expect(JSON.parse(answer as string)).toMatchObject({ ok: true, total: 60, cases: [{ id: 1, filing_date: null }] });
  });

  it('answers a failed search with an error result', async () => {
    const form = renderAt(<CaseSearch />, '/cases/search?party=Smith');
    await settleSearches();
    const agent = respondWithSpy();
    submit(form, true, agent.respondWith);
    const config = { headers: {} } as InternalAxiosRequestConfig;
    await failSearches(new AxiosError('Request failed with status code 503', 'ERR_BAD_RESPONSE', config, null,
      { status: 503, data: {}, statusText: '', headers: {}, config } as AxiosResponse));
    expect(await agent.answer()).toMatchObject({ ok: false, code: 'unavailable', status: 503 });
  });

  it('answers an agent whose search the page closed on', async () => {
    const form = renderAt(<CaseSearch />, '/cases/search?party=Smith');
    await settleSearches();
    const agent = respondWithSpy();
    submit(form, true, agent.respondWith);
    cleanup();
    expect(await agent.answer()).toMatchObject({ ok: false, code: 'cancelled' });
    expect(getAgentActivity()).toEqual([expect.objectContaining({ tool: 'search_cases_form', ok: false })]);
  });

  it('never calls respondWith for a human submission', async () => {
    const form = renderAt(<CaseSearch />, '/cases/search');
    await settleSearches();
    const human = respondWithSpy();
    submit(form, false, human.respondWith);
    await settleSearches();
    expect(human.respondWith).not.toHaveBeenCalled();
  });

  it('still searches and logs where respondWith is missing or throws', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const form = renderAt(<CaseSearch />, '/cases/search?party=Smith');
    await settleSearches();

    submit(form, true);
    submit(form, true, () => { throw new DOMException('Not dispatching', 'InvalidStateError'); });
    expect(searchCases).toHaveBeenCalledTimes(3);
    await settleSearches();
    expect(warn).toHaveBeenCalledOnce();
    // The second submission replaced the first one's search before it settled.
    expect(getAgentActivity().map(entry => entry.ok)).toEqual([true, false]);
  });

  it('searches for the values an agent filled in, even without input events', async () => {
    const form = renderAt(<CaseSearch />, '/cases/search');
    await settleSearches();
    const party = screen.getByLabelText<HTMLInputElement>('Party Name');
    // Set the DOM value the way a script can, leaving React's state behind.
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(party, 'Doe');
    submit(form, true);
    expect(searchCases).toHaveBeenLastCalledWith(expect.objectContaining({ party_name: 'Doe' }), expect.anything());
  });
});

describe('agent hub search form', () => {
  it('logs only agent submissions, timed around the search', async () => {
    const form = renderAt(<AgentDeclarativeSearch />, '/agent');
    submit(form, false);
    await settleSearches();
    expect(searchCases).toHaveBeenCalledTimes(1);
    expect(getAgentActivity()).toEqual([]);

    submit(form, true);
    await settleSearches({ afterMs: 30 });
    const [entry, ...rest] = getAgentActivity();
    expect(rest).toEqual([]);
    expect(entry).toMatchObject({ tool: 'search_cases_form', ok: true });
    expect(entry.summary).toContain('surface=agent_hub');
    expect(entry.durationMs).toBeGreaterThanOrEqual(25);
  });

  it('answers the agent through respondWith with what the imperative search_cases tool returns', async () => {
    const form = renderAt(<AgentDeclarativeSearch />, '/agent');
    const agent = respondWithSpy();
    submit(form, true, agent.respondWith);
    expect(agent.respondWith).toHaveBeenCalledOnce();
    await settleSearches({ result: THREE_PAGES });
    expect(await agent.respondWith.mock.calls[0][0]).toBe(await imperativeResult({ party_name: 'Smith' }, THREE_PAGES));

    const failing = respondWithSpy();
    submit(form, true, failing.respondWith);
    await failSearches();
    expect(await failing.answer()).toMatchObject({ ok: false, code: 'unavailable' });
  });
});

describe('form tool names', () => {
  it('differ from every imperative tool name, so both register in a host with one name map', () => {
    // Chrome keeps one tool map per document: a form holding a name makes registerTool reject it.
    const sources = import.meta.glob(['../**/*.tsx', '!../**/*.test.tsx'], { query: '?raw', import: 'default', eager: true });
    const formNames = Object.values(sources).flatMap(source => [...(source as string).matchAll(/toolname="([^"]+)"/g)]
      .map(match => match[1]));
    expect(formNames).toEqual(expect.arrayContaining(['search_cases_form', 'review_queue_form']));
    const imperative = new Set<string>(TOOL_DEFINITIONS.map(tool => tool.name));
    expect(formNames.filter(name => imperative.has(name))).toEqual([]);
  });
});
