import { getDemoRole } from '../components/auth/LoginScreen';
import { catalogForRole, registerCatalogTool, toolsForRole } from './catalog';
import { publishAgentPageContext } from './context';
import { createLoggingModelContext } from './registerTool';
import type { ModelContext } from './types';
import { registerAuthTools } from './tools/auth';
import { registerClerkTools } from './tools/clerk';
import { registerCourtTools } from './tools/courts';
import { registerExtendedFilingTools } from './tools/filings-ext';
import { registerFilingNavTools } from './tools/filings-nav';
import { registerNavigationTools } from './tools/navigation';
import { registerOrchestrationTools } from './tools/orchestration';
import { registerRulesTools } from './tools/rules';
import { registerSearchTools } from './tools/search';
import { registerSessionTools } from './tools/session';
import { registerWorkflowTools } from './tools/workflows';

let controller: AbortController | null = null;
let lastRole: string | null | undefined;
let initialized = false;
let lateBindTimer: ReturnType<typeof setInterval> | null = null;

async function registerRoleTools(mc: ModelContext, role: string | null, signal: AbortSignal) {
  const logMc = createLoggingModelContext(mc);

  await registerCatalogTool(logMc, role, signal);
  await registerSessionTools(logMc, signal);
  await registerSearchTools(logMc, signal);
  await registerCourtTools(logMc, signal);
  await registerRulesTools(logMc, signal);
  await registerOrchestrationTools(logMc, signal);
  await registerWorkflowTools(logMc, signal);
  await registerNavigationTools(logMc, signal);
  await registerAuthTools(logMc, signal);

  const allowed = toolsForRole(role);

  if (allowed.has('list_my_filings')) {
    await registerExtendedFilingTools(logMc, signal);
    await registerFilingNavTools(logMc, signal);
  }
  if (allowed.has('get_clerk_review_queue')) {
    await registerClerkTools(logMc, signal);
  }

  publishAgentPageContext(mc);
}

export async function refreshMuefsWebMcpTools(): Promise<void> {
  if (!document.modelContext) return;

  const role = getDemoRole();
  if (controller && lastRole === role) return;

  controller?.abort();
  controller = new AbortController();
  lastRole = role;

  await registerRoleTools(document.modelContext, role, controller.signal);

  if (import.meta.env.DEV) {
    const names = catalogForRole(role).map((t) => t.name);
    console.info(`[MUEFS WebMCP] Registered ${names.length} tools for role=${role || 'anonymous'}`, names);
  }
}

function onHostToolChange(): void {
  window.dispatchEvent(new CustomEvent('muefs-webmcp-tools-changed'));
  publishAgentPageContext();
}

function wireHostListeners(mc: ModelContext): void {
  if (typeof mc.addEventListener === 'function') {
    mc.addEventListener('toolchange', onHostToolChange);
  } else {
    const prev = mc.ontoolchange;
    mc.ontoolchange = (event: Event) => {
      if (typeof prev === 'function') prev(event);
      onHostToolChange();
    };
  }
}

export function initMuefsWebMcp(): void {
  if (initialized) return;
  initialized = true;

  const boot = () => {
    if (!document.modelContext) return false;
    wireHostListeners(document.modelContext);
    refreshMuefsWebMcpTools().catch((err) => {
      if (import.meta.env.DEV) console.debug('[MUEFS WebMCP] registration failed:', err);
    });
    return true;
  };

  if (!boot() && typeof window !== 'undefined') {
    let attempts = 0;
    lateBindTimer = setInterval(() => {
      attempts += 1;
      if (boot() || attempts > 40) {
        if (lateBindTimer) clearInterval(lateBindTimer);
        lateBindTimer = null;
      }
    }, 250);
  }

  window.addEventListener('muefs-demo-role-changed', () => {
    lastRole = undefined;
    refreshMuefsWebMcpTools().catch(() => {});
  });

  window.addEventListener('storage', (event) => {
    if (event.key === 'demo_role') {
      lastRole = undefined;
      refreshMuefsWebMcpTools().catch(() => {});
    }
  });

  window.addEventListener('popstate', () => publishAgentPageContext());
  window.addEventListener('beforeunload', () => controller?.abort());
}

export function webMcpStatus(): { available: boolean; role: string | null; toolCount: number } {
  const role = getDemoRole();
  return {
    available: Boolean(document.modelContext),
    role,
    toolCount: catalogForRole(role).length,
  };
}

export async function listRegisteredToolsFromBrowser(): Promise<string[]> {
  if (!document.modelContext?.getTools) return catalogForRole(getDemoRole()).map((t) => t.name);
  try {
    const tools = await document.modelContext.getTools();
    return tools.map((t) => t.name);
  } catch {
    return [];
  }
}
