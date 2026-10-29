import type { ToolExecutors } from '../definitions';
import { toolOk } from '../output';

export const filingNavTools = {
  // The schema check (registerTools.ts) guarantees integer ids, so the path holds only ids.
  async start_motion_filing(input) {
    const params = new URLSearchParams({
      case_id: String(input.case_id),
      court_id: String(input.court_id),
      case_type_id: String(input.case_type_id),
    });
    if (input.service_only === true) {
      params.set('service_only', 'true');
    }
    return toolOk({
      path: `/filing/new?${params}`,
      hint: 'Open this path in MUEFS or call navigate_to with this path.',
    });
  },
} satisfies ToolExecutors;
