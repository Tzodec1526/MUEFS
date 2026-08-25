import { hasWebMcp } from './types';
import { registerSearchTools } from './tools/search';
import { registerFilingTools } from './tools/filings';
import { registerClerkTools } from './tools/clerk';
import { registerDemoTools } from './tools/demo';
import { registerFilingNavTools } from './tools/filings-nav';

let registered = false;

/** Register MUEFS WebMCP tools when the browser supports document.modelContext. */
export async function registerMuefsWebMcpTools(): Promise<void> {
  if (registered || !hasWebMcp() || !document.modelContext) return;

  const mc = document.modelContext;
  const controller = new AbortController();

  await registerSearchTools(mc, controller.signal);
  await registerFilingTools(mc, controller.signal);
  await registerClerkTools(mc, controller.signal);
  await registerDemoTools(mc, controller.signal);
  await registerFilingNavTools(mc, controller.signal);

  registered = true;

  if (import.meta.env.DEV) {
    console.info(
      '[MUEFS WebMCP] Tools registered. Enable chrome://flags/#enable-webmcp-testing ' +
        'and use the Model Context Tool Inspector extension to experiment.',
    );
  }

  window.addEventListener('beforeunload', () => controller.abort());
}
