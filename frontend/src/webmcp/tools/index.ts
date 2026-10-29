import type { ToolExecutor, ToolName } from '../definitions';
import { authTools } from './auth';
import { clerkTools } from './clerk';
import { courtTools } from './courts';
import { filingTools } from './filings-ext';
import { filingNavTools } from './filings-nav';
import { navigationTools } from './navigation';
import { rulesTools } from './rules';
import { searchTools } from './search';
import { sessionTools } from './session';
import { workflowTools } from './workflows';

/** One implementation per defined tool; the type fails to compile if a definition lacks one. */
export const TOOL_EXECUTORS: Record<ToolName, ToolExecutor> = {
  ...sessionTools,
  ...searchTools,
  ...courtTools,
  ...rulesTools,
  ...workflowTools,
  ...navigationTools,
  ...authTools,
  ...filingTools,
  ...filingNavTools,
  ...clerkTools,
};
