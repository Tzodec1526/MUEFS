/** What agents are told to do next. Suggestions name only tools registered for the role and build. */

import { isDemoBuild } from '../config/demoMode';
import { toolsForRole } from './catalog';
import { AUDIENCE_ROLES, isClerkRole, isFilerRole, type ToolAudience } from './definitions';

export const HUMAN_IN_THE_LOOP =
  'Agents may research and navigate; the human confirms each navigation or role switch, ' +
  'and only humans submit filings in the wizard.';

const SIGN_IN_AT_LOGIN = 'ask the human to sign in at /login';

export interface NextStep {
  /** A tool registered for this role in this build, or null when the human must act first. */
  tool: string | null;
  hint: string;
}

function preferredStep(role: string | null): NextStep {
  if (!role) {
    return { tool: 'sign_in_demo_role', hint: 'Ask which role the human wants; they confirm the switch.' };
  }
  if (isClerkRole(role)) {
    return { tool: 'clerk_triage_workflow', hint: 'Summarize the review queue; the clerk decides each filing.' };
  }
  if (isFilerRole(role)) {
    return { tool: 'attorney_motion_workflow', hint: 'Plan the motion; the filer submits it in the wizard.' };
  }
  return {
    tool: 'get_agent_catalog',
    hint: 'This session has the public docket tools; filing needs an attorney or self-represented ' +
      'session, and review a clerk session.',
  };
}

export function suggestNextStep(role: string | null): NextStep {
  const step = preferredStep(role);
  if (step.tool && toolsForRole(role).some(tool => tool.name === step.tool)) return step;
  // Without demo sign-in only the human can sign in.
  return { tool: null, hint: `To file or review, ${SIGN_IN_AT_LOGIN}. Public docket tools work without signing in.` };
}

type RestrictedAudience = Exclude<ToolAudience, 'everyone'>;

const AUDIENCE_LABEL: Record<RestrictedAudience, string> = {
  filer: 'an attorney or self-represented litigant',
  clerk: 'a court clerk',
};

/** How an agent gets a session a tool needs: the demo sign-in tool, or the human at /login. */
export function signInRequired(audience: RestrictedAudience): {
  message: string;
  action: { tool: 'sign_in_demo_role'; role: string } | { ask_human: 'sign_in'; path: '/login' };
} {
  const who = AUDIENCE_LABEL[audience];
  const demoRoles = AUDIENCE_ROLES[audience];
  if (isDemoBuild()) {
    return {
      message: `Sign in as ${who} first: call sign_in_demo_role with role ${demoRoles.join(' or ')}.`,
      action: { tool: 'sign_in_demo_role', role: demoRoles[0] },
    };
  }
  return { message: `Sign in as ${who} first: ${SIGN_IN_AT_LOGIN}.`, action: { ask_human: 'sign_in', path: '/login' } };
}

export interface ExamplePrompt {
  title: string;
  /** The role the prompt works in; every tool it names is registered for that role. */
  role: string | null;
  prompt: string;
}

/** Prompts a human can paste into their agent, shown on /agent and returned by get_agent_catalog. */
export function examplePrompts(): ExamplePrompt[] {
  const demo = isDemoBuild();
  const signIn = (role: string, who: string) =>
    demo ? `Sign in as ${role} with sign_in_demo_role.` : `I am signed in as ${who}.`;
  return [
    {
      title: 'Session',
      role: null,
      prompt: 'Call get_agent_session, then get_agent_catalog, and tell me what we can do together here.',
    },
    {
      title: 'Attorney motion',
      role: 'attorney',
      prompt: `${signIn('attorney', 'an attorney')} Run attorney_motion_workflow for party Smith, let me ` +
        'choose a case if there are several matches, navigate_to the filing wizard, then call get_agent_activity.',
    },
    {
      title: 'SRL MCR',
      role: 'srl',
      prompt: `${signIn('srl', 'a self-represented litigant')} Run explain_mcr_for_filing for court_id 3 ` +
        'case_type_id 35 filing_type motion.',
    },
    {
      title: 'Clerk triage',
      role: 'clerk',
      prompt: `${signIn('clerk', 'a court clerk')} Run clerk_triage_workflow, then navigate_to /clerk/queue.`,
    },
  ];
}
