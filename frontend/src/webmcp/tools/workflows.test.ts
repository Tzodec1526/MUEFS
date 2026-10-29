import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { getCase, searchCases, type CaseDocket } from '../../api/cases';
import { getFilingChecklists, getFilingRequirements } from '../../api/courts';
import { getFilingStatusCounts } from '../../api/filings';
import { getDemoRole } from '../../components/auth/LoginScreen';
import { workflowTools } from './workflows';

vi.mock('../../api/cases', () => ({ getCase: vi.fn(), searchCases: vi.fn() }));
vi.mock('../../api/courts', () => ({ getFilingChecklists: vi.fn(), getFilingRequirements: vi.fn() }));
vi.mock('../../api/filings', () => ({ getClerkQueue: vi.fn(), getFilingStatusCounts: vi.fn() }));
vi.mock('../../components/auth/LoginScreen', () => ({
  getDemoRole: vi.fn(), getDemoCourtId: () => 3,
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getDemoRole).mockReturnValue('attorney');
});

afterEach(() => { vi.unstubAllEnvs(); });

async function run(name: keyof typeof workflowTools, input: Record<string, unknown> = {}) {
  return JSON.parse(await workflowTools[name](input) as string);
}

it('returns choices without building a filing plan for an ambiguous search', async () => {
  vi.mocked(searchCases).mockResolvedValue({
    total: 40,
    page: 1,
    page_size: 25,
    cases: [
      { id: 1, title: 'Smith A', case_number: 'A', court_id: 3, case_type_id: 7,
        court_name: 'Court A', court_county: 'Wayne', status: 'open',
        filed_date: '2026-09-01T12:00:00Z', filing_date: null, participants: [] },
      { id: 2, title: 'Smith B', case_number: 'B', court_id: 4, case_type_id: 7,
        court_name: 'Court B', court_county: 'Alcona', status: 'open',
        filed_date: '2026-09-01T12:00:00Z', filing_date: null, participants: [] },
    ],
  });
  const result = await run('attorney_motion_workflow', { party_name: 'Smith' });
  expect(result.needs_case_selection).toBe(true);
  expect(result.total).toBe(40);
  expect(result.candidates.map((c: { id: number }) => c.id)).toEqual([1, 2]);
  expect(result.filing_wizard_path).toBeUndefined();
  expect(getCase).not.toHaveBeenCalled();
  expect(getFilingRequirements).not.toHaveBeenCalled();
});

it('builds the plan for the explicitly chosen case without searching again', async () => {
  vi.mocked(getCase).mockResolvedValue({
    id: 2, title: 'Smith B', case_number: 'B', court_id: 4, case_type_id: 7, can_file: true,
  } as CaseDocket);
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
  vi.mocked(getFilingChecklists).mockResolvedValue([]);
  vi.mocked(getFilingStatusCounts).mockResolvedValue({ draft: 7, accepted: 20 });
  const result = await run('attorney_motion_workflow', { case_id: 2 });
  expect(result.case.id).toBe(2);
  expect(result.draft_filings_pending).toBe(7);
  expect(result.filing_wizard_path).toContain('case_id=2&court_id=4&case_type_id=7');
  expect(searchCases).not.toHaveBeenCalled();
  expect(getFilingRequirements).toHaveBeenCalledWith(4, 7, 'subsequent');
});

it('explains missing filing access without sending a public-case reader to the wizard', async () => {
  vi.mocked(getCase).mockResolvedValue({ id: 2, can_file: false } as CaseDocket);
  const result = await run('attorney_motion_workflow', { case_id: 2 });
  expect(result.needs_case_access).toBe(true);
  expect(result.case_path).toBe('/cases/2');
  expect(result.filing_wizard_path).toBeUndefined();
  expect(getFilingRequirements).not.toHaveBeenCalled();
});

it.each([
  ['attorney_motion_workflow', 'clerk', 'attorney'],
  ['clerk_triage_workflow', 'attorney', 'clerk'],
] as const)('%s asks a %s session to switch roles with the demo sign-in tool', async (name, role, target) => {
  vi.stubEnv('VITE_ALLOW_DEMO_MODE', 'true');
  vi.mocked(getDemoRole).mockReturnValue(role);
  const result = await run(name, { party_name: 'Smith' });
  expect(result).toMatchObject({
    ok: false, code: 'needs_sign_in', action: { tool: 'sign_in_demo_role', role: target },
  });
  expect(searchCases).not.toHaveBeenCalled();
});

it.each(['attorney_motion_workflow', 'clerk_triage_workflow'] as const)(
  '%s sends the human to /login in a build without demo sign-in',
  async (name) => {
    vi.stubEnv('VITE_ALLOW_DEMO_MODE', 'false');
    vi.mocked(getDemoRole).mockReturnValue(null);
    const result = await run(name, { party_name: 'Smith' });
    expect(result).toMatchObject({ ok: false, code: 'needs_sign_in', action: { ask_human: 'sign_in', path: '/login' } });
    expect(JSON.stringify(result)).not.toContain('sign_in_demo_role');
  },
);
