import { initMuefsWebMcp } from './registry';

export { initMuefsWebMcp, refreshMuefsWebMcpTools, webMcpStatus, listRegisteredToolsFromBrowser } from './registry';
export { catalogForRole, TOOL_CATALOG, toolsForRole } from './catalog';
export { getAgentActivity, clearAgentActivity, type AgentActivityEntry } from './activity';
export { hasWebMcp } from './types';
export { publishAgentPageContext } from './context';
export { isSafeAppPath, navigateApp, MUEFS_NAVIGATE_EVENT } from './navigate';

/** Register MUEFS WebMCP tools when the browser supports document.modelContext. */
export function registerMuefsWebMcpTools(): void {
  initMuefsWebMcp();
}
