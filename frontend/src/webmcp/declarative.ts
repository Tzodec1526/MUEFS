/**
 * Declarative WebMCP tools are ordinary forms (toolname="…") that humans submit too. The
 * WebMCP declarative API adds SubmitEvent.agentInvoked, true when an agent made the
 * submission, and SubmitEvent.respondWith(), which hands the agent the tool's result:
 * https://github.com/webmachinelearning/webmcp/blob/main/declarative-api-explainer.md
 * Only agent submissions belong in the agent activity feed, and each gets exactly one answer.
 */

import { agentActivityEpoch, logAgentActivity } from './activity';
import { toolError, toolOk } from './output';

/** A native submit event, or a React synthetic event wrapping one. */
export type SubmitEventLike = Event | { nativeEvent: Event };

function nativeEventOf(event: SubmitEventLike): Event {
  return 'nativeEvent' in event ? event.nativeEvent : event;
}

export function isAgentInvokedSubmit(event: SubmitEventLike): boolean {
  // Browsers without the declarative API leave the attribute undefined.
  return (nativeEventOf(event) as Event & { agentInvoked?: unknown }).agentInvoked === true;
}

/**
 * Give the agent that submitted a form the tool result `response` settles to, through
 * SubmitEvent.respondWith(). Call it while the submit event is dispatched, after
 * preventDefault(): the explainer requires both, and Chrome throws otherwise. Browsers without
 * respondWith, submissions left to the browser, and human submissions are left alone; this
 * never throws. Returns whether the browser took the response.
 */
export function respondToAgent(event: SubmitEventLike, response: Promise<string>): boolean {
  if (!isAgentInvokedSubmit(event)) return false;
  const native = nativeEventOf(event) as Event & { respondWith?: unknown };
  if (typeof native.respondWith !== 'function' || !native.defaultPrevented) return false;
  try {
    native.respondWith(response);
    return true;
  } catch (err) {
    // For example, a browser that only accepts it before the event finished dispatching.
    console.warn('[MUEFS WebMCP] SubmitEvent.respondWith failed:', err);
    return false;
  }
}

/**
 * Settles an agent's form submission once the work it started has settled: logs the call
 * and answers the agent with `response`, the tool result (JSON, as the imperative tools
 * return). Only the first call counts.
 */
export type AgentSubmission = (ok: boolean, response?: string) => void;

/**
 * Start timing a declarative tool form submission; call it from the submit handler after
 * preventDefault(). For an agent-invoked submission this answers the agent through
 * respondWith() when the browser supports it, and returns the callback that logs the call
 * once, measured from now, and sends that answer. For a human submission it returns null.
 */
export function trackAgentSubmission(
  event: SubmitEventLike,
  tool: string,
  input: Record<string, unknown>,
): AgentSubmission | null {
  if (!isAgentInvokedSubmit(event)) return null;
  const started = performance.now();
  const since = agentActivityEpoch();
  let answer: (response: string) => void = () => {};
  respondToAgent(event, new Promise<string>(resolve => { answer = resolve; }));
  let settled = false;
  return (ok, response) => {
    if (settled) return;
    settled = true;
    const ms = Math.round(performance.now() - started);
    logAgentActivity(tool, { ...input, via: 'declarative_form' }, ok, ms, since);
    answer(response ?? (ok ? toolOk({}) : toolError('The form submission did not complete.', 'unavailable')));
  };
}
