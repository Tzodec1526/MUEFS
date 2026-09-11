import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getCase, searchCases } from '../api/cases';
import { getFilingChecklists, getFilingRequirements } from '../api/courts';
import { getClerkQueue, listFilings } from '../api/filings';
import { getDemoCourtId, getDemoRole } from '../components/auth/LoginScreen';
import { registerOrchestrationTools } from './tools/orchestration';
import { registerWorkflowTools } from './tools/workflows';
import type { ModelContext, ModelContextTool } from './types';

vi.mock('../api/cases', () => ({ searchCases: vi.fn(), getCase: vi.fn() }));
vi.mock('../api/courts', () => ({ getFilingRequirements: vi.fn(), getFilingChecklists: vi.fn() }));
vi.mock('../api/filings', () => ({ listFilings: vi.fn(), getClerkQueue: vi.fn() }));
vi.mock('../components/auth/LoginScreen', () => ({ getDemoRole: vi.fn(), getDemoCourtId: vi.fn() }));

const calls: string[] = [];

function track<T extends (...args: never[]) => unknown>(fn: T, name: string, value: unknown) {
  vi.mocked(fn).mockImplementation((async () => {
    calls.push(name);
    return value;
  }) as unknown as T);
}

const docket = {
  id: 7,
  case_number: '24-000123-CZ',
  title: 'Smith v Jones',
  status: 'open',
  court_id: 3,
  case_type_id: 11,
  is_sealed: false,
  participants: [{ party_name: 'Smith', role: 'plaintiff' }],
};

const requirements = [
  { id: 1, document_type_code: 'MOT', is_required: true, description: 'Motion', mcr_reference: 'MCR 2.119(A)' },
  { id: 2, document_type_code: 'EXH', is_required: false, description: 'Exhibits', mcr_reference: null },
];

const checklists = [
  {
    id: 1,
    motion_type: 'motion_for_summary_disposition',
    checklist_items: {
      items: [
        { label: 'Brief in support', required: true },
        { label: 'Proposed order', required: true },
        { label: 'Notice of hearing', required: false },
      ],
    },
    help_text: null,
    mcr_url: null,
  },
];

async function collectTools(register: (mc: ModelContext) => Promise<void>) {
  const tools = new Map<string, ModelContextTool>();
  const mc = {
    registerTool: async (tool: ModelContextTool) => {
      tools.set(tool.name, tool);
    },
  } as unknown as ModelContext;
  await register(mc);
  return tools;
}

async function run(tools: Map<string, ModelContextTool>, name: string, input: Record<string, unknown> = {}) {
  const tool = tools.get(name);
  if (!tool) throw new Error(`tool ${name} not registered`);
  return JSON.parse((await tool.execute(input)) as string);
}

beforeEach(() => {
  vi.resetAllMocks();
  calls.length = 0;
  track(searchCases, 'search', { cases: [docket], total: 1 });
  track(getCase, 'getCase', docket);
  track(getFilingRequirements, 'requirements', requirements);
  track(getFilingChecklists, 'checklists', checklists);
  track(listFilings, 'listFilings', { filings: [], total: 2 });
  vi.mocked(getDemoRole).mockReturnValue('attorney');
  vi.mocked(getDemoCourtId).mockReturnValue(3);
});

describe('attorney_motion_workflow', () => {
  it('searches, opens the docket, then loads requirements and checklists', async () => {
    const tools = await collectTools(registerWorkflowTools);
    const result = await run(tools, 'attorney_motion_workflow', { party_name: 'Smith' });

    expect(calls.slice(0, 2)).toEqual(['search', 'getCase']);
    expect(calls.slice(2).sort()).toEqual(['checklists', 'listFilings', 'requirements']);
    expect(getFilingRequirements).toHaveBeenCalledWith(3, 11, 'subsequent');
    expect(getFilingChecklists).toHaveBeenCalledWith(3, 11);

    expect(result.ok).toBe(true);
    expect(result.required_documents).toEqual([{ code: 'MOT', label: 'Motion', mcr: 'MCR 2.119(A)' }]);
    expect(result.motion_checklists).toEqual([
      {
        motion_type: 'motion_for_summary_disposition',
        required_items: ['Brief in support', 'Proposed order'],
        help_text: null,
      },
    ]);
    expect(result.plan).toEqual([
      'Review Smith v Jones (24-000123-CZ).',
      'Resume or discard 2 pending draft filing(s) before starting a new one.',
      'Prepare required documents: Motion (MCR 2.119(A)).',
      'For a motion_for_summary_disposition, include: Brief in support, Proposed order.',
      'Open the pre-filled wizard — upload PDFs — human submits.',
    ]);
    expect(result.filing_wizard_path).toContain('case_id=7');
  });

  it('asks for sign-in when the role is not a filer', async () => {
    vi.mocked(getDemoRole).mockReturnValue('public');
    const tools = await collectTools(registerWorkflowTools);
    const result = await run(tools, 'attorney_motion_workflow', { party_name: 'Smith' });

    expect(result.needs_sign_in).toBe(true);
    expect(result.action).toEqual({ tool: 'sign_in_demo_role', role: 'attorney' });
    expect(calls).toEqual([]);
  });

  it('returns found=false and stops when search has no match', async () => {
    track(searchCases, 'search', { cases: [], total: 0 });
    const tools = await collectTools(registerWorkflowTools);
    const result = await run(tools, 'attorney_motion_workflow', { case_number: 'nope' });

    expect(result).toEqual({ ok: true, found: false, message: 'No public case match.' });
    expect(calls).toEqual(['search']);
  });

  it('errors on a sealed case before loading requirements', async () => {
    track(getCase, 'getCase', { ...docket, is_sealed: true });
    const tools = await collectTools(registerWorkflowTools);
    const result = await run(tools, 'attorney_motion_workflow', { party_name: 'Smith' });

    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/sealed/i);
    expect(calls).toEqual(['search', 'getCase']);
  });
});

describe('clerk_triage_workflow', () => {
  it('asks for clerk sign-in for other roles', async () => {
    vi.mocked(getDemoRole).mockReturnValue('attorney');
    const tools = await collectTools(registerWorkflowTools);
    const result = await run(tools, 'clerk_triage_workflow');

    expect(result.needs_sign_in).toBe(true);
    expect(result.action).toEqual({ tool: 'sign_in_demo_role', role: 'clerk' });
    expect(getClerkQueue).not.toHaveBeenCalled();
  });

  it('loads submitted and under_review queues for the clerk court', async () => {
    vi.mocked(getDemoRole).mockReturnValue('clerk');
    vi.mocked(getClerkQueue).mockImplementation(async (_courtId, _page, status) => ({
      filings: [
        {
          id: status === 'submitted' ? 1 : 2,
          case_title: `Case ${status}`,
          status,
          submitted_at: '2026-01-01T00:00:00Z',
        },
      ] as never,
      total: status === 'submitted' ? 4 : 1,
    }));
    const tools = await collectTools(registerWorkflowTools);
    const result = await run(tools, 'clerk_triage_workflow');

    expect(getClerkQueue).toHaveBeenCalledWith(3, 1, 'submitted');
    expect(getClerkQueue).toHaveBeenCalledWith(3, 1, 'under_review');
    expect(result.court_id).toBe(3);
    expect(result.submitted_count).toBe(4);
    expect(result.under_review_count).toBe(1);
    expect(result.priority_filings.map((f: { id: number }) => f.id)).toEqual([1, 2]);
    expect(result.queue_path).toBe('/clerk/queue');
  });
});

describe('research_case_for_motion', () => {
  it('searches, opens the docket, then loads checklists and derives next_steps', async () => {
    const tools = await collectTools(registerOrchestrationTools);
    const result = await run(tools, 'research_case_for_motion', { party_name: 'Smith' });

    expect(calls).toEqual(['search', 'getCase', 'checklists']);
    expect(getFilingRequirements).not.toHaveBeenCalled();
    expect(result.found).toBe(true);
    expect(result.search_hit.id).toBe(7);
    expect(result.motion_checklists[0].required_items).toEqual(['Brief in support', 'Proposed order']);
    expect(result.next_steps).toEqual([
      'Sign in as attorney or self-represented litigant if not already.',
      'Open the pre-filled filing wizard URL.',
      'For a motion_for_summary_disposition, upload: Brief in support, Proposed order.',
      'Human filer reviews and submits — agent does not submit alone.',
    ]);
  });

  it('falls back to a generic step when no checklist is returned', async () => {
    track(getFilingChecklists, 'checklists', []);
    const tools = await collectTools(registerOrchestrationTools);
    const result = await run(tools, 'research_case_for_motion', { case_id: 7 });

    expect(calls).toEqual(['getCase', 'checklists']);
    expect(result.search_hit).toBeNull();
    expect(result.next_steps[2]).toMatch(/No motion checklist returned/);
  });

  it('returns found=false and stops when search has no match', async () => {
    track(searchCases, 'search', { cases: [], total: 0 });
    const tools = await collectTools(registerOrchestrationTools);
    const result = await run(tools, 'research_case_for_motion', { case_number: 'nope' });

    expect(result.found).toBe(false);
    expect(calls).toEqual(['search']);
  });

  it('errors on a sealed case before loading checklists', async () => {
    track(getCase, 'getCase', { ...docket, is_sealed: true });
    const tools = await collectTools(registerOrchestrationTools);
    const result = await run(tools, 'research_case_for_motion', { party_name: 'Smith' });

    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/sealed/i);
    expect(calls).toEqual(['search', 'getCase']);
  });
});
