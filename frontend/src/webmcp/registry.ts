import { getDemoRole } from '../components/auth/LoginScreen';
import { catalogForRole } from './catalog';
import { publishAgentPageContext } from './context';
import type { ModelContext } from './types';

let controller: AbortController | null = null;
let lastRole: string | null | undefined;
let initialized = false;
let lateBindTimer: ReturnType<typeof setInterval> | null = null;

export async function refreshMuefsWebMcpTools(): Promise<void> {
  if (!document.modelContext) return;

  const role = getDemoRole();
  if (controller && lastRole === role) return;

  controller?.abort();
  const activeController = new AbortController();
  controller = activeController;
  lastRole = role;

  try {
    const { registerRoleTools } = await import('./registerTools');
    if (activeController.signal.aborted) return;
    await registerRoleTools(document.modelContext, role, activeController.signal);
  } catch (err) {
    activeController.abort();
    if (controller === activeController) controller = null;
    throw err;
  }

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
  if (!document.modelContext?.getTools) return [];
  try {
    const tools = await document.modelContext.getTools();
    return tools.map((t) => t.name);
  } catch {
    return [];
  }
}
