import { getDemoRole } from '../components/auth/LoginScreen';
import { roleMayUse, toolsForRole } from './catalog';
import type { ToolDefinition, ToolName } from './definitions';
import { signInRequired } from './guidance';
import { checkToolInput } from './input';
import { apiErrorResult, toolError } from './output';
import { createLoggingModelContext } from './registerTool';
import { TOOL_EXECUTORS } from './tools';
import type { ModelContext, ModelContextTool } from './types';

/** The host-facing tool for a definition, bound to its implementation. */
function bindTool(tool: ToolDefinition<ToolName>, role: string | null): ModelContextTool {
  const { name, title, description, inputSchema, annotations, audience } = tool;
  const implementation = TOOL_EXECUTORS[name];
  return {
    name,
    title,
    description,
    inputSchema,
    annotations,
    async execute(rawInput) {
      // The role can change before the host drops this pass's tools.
      if (audience !== 'everyone' && !roleMayUse(tool, getDemoRole())) {
        const { message, action } = signInRequired(audience);
        return toolError(message, 'needs_sign_in', { action });
      }
      // Nothing an implementation puts into an API path or query escapes its schema.
      const checked = checkToolInput(inputSchema, rawInput);
      if (!checked.ok) return toolError(checked.error, 'invalid');
      try {
        return await implementation(checked.input, { role });
      } catch (err) {
        // API failures become results with stable codes; programming errors still throw.
        const result = apiErrorResult(err);
        if (result === null) throw err;
        return result;
      }
    },
  };
}

export async function registerRoleTools(mc: ModelContext, role: string | null, signal: AbortSignal) {
  const logMc = createLoggingModelContext(mc);
  for (const tool of toolsForRole(role)) {
    // A newer role's pass replaces this one; do not register its stale tools.
    if (signal.aborted) return;
    try {
      await logMc.registerTool(bindTool(tool, role), { signal });
    } catch (err) {
      if (signal.aborted) return;
      // One rejected tool (say, a name the page already uses) must not cost the others.
      console.warn(`[MUEFS WebMCP] Could not register ${tool.name}:`, err);
    }
  }
}
