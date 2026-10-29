import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearAgentActivity, getAgentActivity } from './activity';
import { isAgentInvokedSubmit, respondToAgent, trackAgentSubmission } from './declarative';

function submitEvent(agentInvoked?: unknown, respondWith?: unknown): Event {
  const event = new Event('submit', { bubbles: true, cancelable: true });
  if (agentInvoked !== undefined) Object.defineProperty(event, 'agentInvoked', { value: agentInvoked });
  if (respondWith !== undefined) Object.defineProperty(event, 'respondWith', { value: respondWith });
  return event;
}

/** An agent submission the page has taken over, as the explainer requires before respondWith. */
function preventedAgentSubmit(respondWith?: unknown): Event {
  const event = submitEvent(true, respondWith);
  event.preventDefault();
  return event;
}

afterEach(() => {
  vi.restoreAllMocks();
  clearAgentActivity();
});

describe('isAgentInvokedSubmit', () => {
  it('reads SubmitEvent.agentInvoked from native and React events', () => {
    expect(isAgentInvokedSubmit(submitEvent(true))).toBe(true);
    expect(isAgentInvokedSubmit({ nativeEvent: submitEvent(true) })).toBe(true);
  });

  it.each([false, undefined, 'true', 1])('treats agentInvoked=%j as a human submission', value => {
    expect(isAgentInvokedSubmit(submitEvent(value))).toBe(false);
    expect(isAgentInvokedSubmit({ nativeEvent: submitEvent(value) })).toBe(false);
  });
});

describe('respondToAgent', () => {
  it('hands the response to SubmitEvent.respondWith', async () => {
    const respondWith = vi.fn();
    const response = Promise.resolve('{"ok":true}');
    expect(respondToAgent({ nativeEvent: preventedAgentSubmit(respondWith) }, response)).toBe(true);
    expect(respondWith).toHaveBeenCalledWith(response);
  });

  it('does nothing, without throwing, in a browser without respondWith', () => {
    expect(respondToAgent(preventedAgentSubmit(), Promise.resolve('{}'))).toBe(false);
  });

  it('leaves human submissions and submissions not taken over by the page alone', () => {
    const respondWith = vi.fn();
    const human = submitEvent(false, respondWith);
    human.preventDefault();
    expect(respondToAgent(human, Promise.resolve('{}'))).toBe(false);
    expect(respondToAgent(submitEvent(true, respondWith), Promise.resolve('{}'))).toBe(false);
    expect(respondWith).not.toHaveBeenCalled();
  });

  it('swallows a respondWith that throws', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const event = preventedAgentSubmit(() => { throw new DOMException('Not dispatching', 'InvalidStateError'); });
    expect(respondToAgent(event, Promise.resolve('{}'))).toBe(false);
    expect(warn).toHaveBeenCalledOnce();
  });
});

describe('trackAgentSubmission', () => {
  it('logs nothing for a human submission', () => {
    expect(trackAgentSubmission(submitEvent(false), 'search_cases_form', { party_name: 'Smith' })).toBeNull();
    expect(getAgentActivity()).toEqual([]);
  });

  it('logs an agent submission once, timed from submit to settle', () => {
    vi.spyOn(performance, 'now').mockReturnValueOnce(1000).mockReturnValueOnce(1042.4);
    const report = trackAgentSubmission(submitEvent(true), 'search_cases_form', { party_name: 'Smith' });
    expect(getAgentActivity()).toEqual([]);

    report!(false);
    report!(true);

    expect(getAgentActivity()).toEqual([expect.objectContaining({
      tool: 'search_cases_form', ok: false, durationMs: 42,
      summary: 'search_cases_form (party_name=Smith, via=declarative_form)',
    })]);
  });

  it('answers the agent once, with the result it settles with', async () => {
    const respondWith = vi.fn();
    const report = trackAgentSubmission(preventedAgentSubmit(respondWith), 'search_cases_form', {});
    expect(respondWith).toHaveBeenCalledOnce();
    report!(true, '{"ok":true,"total":3}');
    report!(false, '{"ok":false}');
    expect(await respondWith.mock.calls[0][0]).toBe('{"ok":true,"total":3}');
  });

  it('answers with a plain result when the form gives none', async () => {
    const answers = [true, false].map(ok => {
      const respondWith = vi.fn();
      trackAgentSubmission(preventedAgentSubmit(respondWith), 'review_queue_form', {})!(ok);
      return respondWith.mock.calls[0][0].then((text: string) => JSON.parse(text));
    });
    expect(await Promise.all(answers)).toEqual([
      { ok: true },
      expect.objectContaining({ ok: false, code: 'unavailable' }),
    ]);
  });
});
