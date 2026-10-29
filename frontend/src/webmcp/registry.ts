import { SESSION_KEY } from '../auth/keycloak';
import { getDemoRole } from '../components/auth/LoginScreen';
import { bindAgentActivity } from './activity';
import { catalogForRole } from './catalog';
import type { ModelContext } from './types';

let controller: AbortController | null = null;
let lastRole: string | null | undefined;
let initialized = false;
let lateBindTimer: ReturnType<typeof setInterval> | null = null;

/**
 * The browser's WebMCP object: document.modelContext, where the spec and Chrome 150+ put it,
 * or navigator.modelContext, its location before (Chrome 146 to 149 have only that one).
 */
export function browserModelContext(): ModelContext | undefined {
  if (typeof document !== 'undefined' && document.modelContext) return document.modelContext;
  return typeof navigator !== 'undefined' ? navigator.modelContext ?? undefined : undefined;
}

export async function refreshMuefsWebMcpTools(): Promise<void> {
  const mc = browserModelContext();
  if (!mc) return;

  const role = getDemoRole();
  // Registration depends only on the role; an aborted pass must be able to retry.
  if (controller && !controller.signal.aborted && lastRole === role) return;

  controller?.abort();
  const activeController = new AbortController();
  controller = activeController;
  lastRole = role;

  try {
    const { registerRoleTools } = await import('./registerTools');
    if (activeController.signal.aborted) return;
    await registerRoleTools(mc, role, activeController.signal);
  } catch (err) {
    activeController.abort();
    if (controller === activeController) controller = null;
    throw err;
  }

  if (activeController.signal.aborted) return;
  // Hosts need not emit toolchange when our initial registration finishes.
  window.dispatchEvent(new CustomEvent('muefs-webmcp-tools-changed'));

  if (import.meta.env.DEV) {
    const names = catalogForRole(role).map((t) => t.name);
    console.info(`[MUEFS WebMCP] Registered ${names.length} tools for role=${role || 'anonymous'}`, names);
  }
}

function onHostToolChange(): void {
  window.dispatchEvent(new CustomEvent('muefs-webmcp-tools-changed'));
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

/** The signed-in session and role the agent activity log belongs to. */
function activitySession(): string {
  let marker: string | null = null;
  try {
    marker = localStorage.getItem(SESSION_KEY);
  } catch {
    /* storage unavailable: the role alone identifies the session */
  }
  return JSON.stringify([marker, getDemoRole()]);
}

export function initMuefsWebMcp(): void {
  if (initialized) return;
  initialized = true;

  const refresh = () => {
    refreshMuefsWebMcpTools().catch((err) => {
      console.warn('[MUEFS WebMCP] tool registration failed:', err);
    });
  };
  // Another account's or role's tool calls must not show in this one's activity feed.
  const onSessionChange = () => {
    bindAgentActivity(activitySession());
    refresh();
  };
  // The session may have changed while this tab was discarded, or closed and restored.
  bindAgentActivity(activitySession());

  const boot = () => {
    const mc = browserModelContext();
    if (!mc) return false;
    wireHostListeners(mc);
    refresh();
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

  // Sign-in, sign-out, role switches, and also profile refreshes and court switches, which
  // keep the session (bindAgentActivity then keeps the log).
  window.addEventListener('muefs-demo-role-changed', onSessionChange);
  // Another tab signed in, signed out or switched roles (a null key: storage was cleared).
  window.addEventListener('storage', (event) => {
    if (event.key === null || event.key === SESSION_KEY || event.key === 'demo_role') onSessionChange();
  });
}

export function webMcpStatus(): { available: boolean; role: string | null; toolCount: number } {
  const role = getDemoRole();
  return {
    available: Boolean(browserModelContext()),
    role,
    toolCount: catalogForRole(role).length,
  };
}

export async function listRegisteredToolsFromBrowser(): Promise<string[]> {
  const mc = browserModelContext();
  if (!mc?.getTools) return [];
  try {
    const tools = await mc.getTools();
    return tools.map((t) => t.name);
  } catch {
    return [];
  }
}
