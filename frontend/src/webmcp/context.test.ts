import { afterEach, expect, it, vi } from 'vitest';
import { buildAgentPageContext } from './context';
import { TOOL_DEFINITIONS } from './definitions';

vi.mock('../components/auth/LoginScreen', () => ({ getDemoRole: () => 'clerk' }));

afterEach(() => { vi.unstubAllGlobals(); });

it.each([
  ['/cases/search', ['search_cases_form']],
  ['/clerk/queue', ['search_cases_form', 'review_queue_form']],
])('names the form tools on %s, none of them an imperative tool', (pathname, names) => {
  vi.stubGlobal('window', { location: { pathname, search: '' } });
  const { declarative_tools_on_site: forms } = buildAgentPageContext();
  expect(forms).toEqual(names);
  const imperative = new Set<string>(TOOL_DEFINITIONS.map(tool => tool.name));
  expect(forms.filter(name => imperative.has(name))).toEqual([]);
});
