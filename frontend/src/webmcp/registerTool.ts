import { logAgentActivity } from './activity';
import type { ModelContext, ModelContextRegisterOptions, ModelContextTool } from './types';

export async function registerMuefsTool(
  mc: ModelContext,
  tool: ModelContextTool,
  options?: ModelContextRegisterOptions,
): Promise<void> {
  const wrapped: ModelContextTool = {
    ...tool,
    async execute(input: Record<string, unknown>) {
      const started = performance.now();
      try {
        const result = await tool.execute(input);
        const ms = Math.round(performance.now() - started);
        let ok = true;
        if (typeof result === 'string') {
          try {
            const parsed = JSON.parse(result) as { ok?: boolean };
            if (parsed && parsed.ok === false) ok = false;
          } catch {
            /* non-JSON success string */
          }
        }
        logAgentActivity(tool.name, input, ok, ms);
        return result;
      } catch (err) {
        const ms = Math.round(performance.now() - started);
        logAgentActivity(tool.name, input, false, ms);
        throw err;
      }
    },
  };
  await mc.registerTool(wrapped, options);
}

/** Proxy that logs every tool registration and execution. */
export function createLoggingModelContext(mc: ModelContext): ModelContext {
  return {
    registerTool: (tool, options) => registerMuefsTool(mc, tool, options),
    getTools: mc.getTools?.bind(mc),
    executeTool: mc.executeTool?.bind(mc),
    provideContext: mc.provideContext?.bind(mc),
    ontoolchange: mc.ontoolchange,
    addEventListener: mc.addEventListener?.bind(mc),
    removeEventListener: mc.removeEventListener?.bind(mc),
  };
}
