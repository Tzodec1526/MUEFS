import { registerCatalogTool, toolsForRole } from './catalog';
import { publishAgentPageContext } from './context';
import { createLoggingModelContext } from './registerTool';
import type { ModelContext } from './types';
import { registerAuthTools } from './tools/auth';
import { registerClerkTools } from './tools/clerk';
import { registerCourtTools } from './tools/courts';
import { registerExtendedFilingTools } from './tools/filings-ext';
import { registerFilingNavTools } from './tools/filings-nav';
import { registerNavigationTools } from './tools/navigation';
import { registerRulesTools } from './tools/rules';
import { registerSearchTools } from './tools/search';
import { registerSessionTools } from './tools/session';
import { registerWorkflowTools } from './tools/workflows';

export async function registerRoleTools(mc: ModelContext, role: string | null, signal: AbortSignal) {
  const logMc = createLoggingModelContext(mc);

  await registerCatalogTool(logMc, role, signal);
  await registerSessionTools(logMc, signal);
  await registerSearchTools(logMc, signal);
  await registerCourtTools(logMc, signal);
  await registerRulesTools(logMc, signal);
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
