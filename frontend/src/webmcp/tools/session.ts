import { getFilingStatusCounts } from '../../api/filings';
import { getDemoRole } from '../../components/auth/LoginScreen';
import { getAgentActivity } from '../activity';
import { catalogForRole } from '../catalog';
import { buildAgentPageContext } from '../context';
import { isFilerRole, type ToolExecutors } from '../definitions';
import { examplePrompts, HUMAN_IN_THE_LOOP, suggestNextStep } from '../guidance';
import { toolOk } from '../output';

export const sessionTools = {
  async get_agent_catalog(_input, { role }) {
    // Describe this registration pass, the tools the host actually has.
    const entries = catalogForRole(role);
    const next = suggestNextStep(role);
    return toolOk({
      role: role || 'anonymous',
      tool_count: entries.length,
      tools: entries,
      workflows: entries.filter(t => t.tier === 'workflow').map(t => t.name),
      suggested_next_tool: next.tool,
      next_step: next.hint,
      human_in_the_loop: HUMAN_IN_THE_LOOP,
      example_prompts: examplePrompts().map(({ title, prompt }) => ({ title, prompt })),
    });
  },

  async get_agent_session() {
    // The session is still worth describing without the count; null says it is unknown.
    let drafts: number | null = 0;
    if (isFilerRole(getDemoRole())) {
      try {
        const counts = await getFilingStatusCounts();
        drafts = counts.draft || 0;
      } catch {
        drafts = null;
      }
    }
    return toolOk({
      ...buildAgentPageContext(),
      origin: window.location.origin,
      draft_filings: drafts,
      recent_activity_count: getAgentActivity().length,
    });
  },

  async get_agent_activity(input) {
    const limit = Math.min(40, Math.max(1, Number(input.limit) || 15));
    const activity = getAgentActivity().slice(0, limit);
    return toolOk({
      count: activity.length,
      activity,
      note: 'Same feed as /agent.',
    });
  },
} satisfies ToolExecutors;
