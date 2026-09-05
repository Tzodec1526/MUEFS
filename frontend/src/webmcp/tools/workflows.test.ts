import { beforeEach, expect, it, vi } from 'vitest';
import { getCase, searchCases } from '../../api/cases';
import { getFilingChecklists, getFilingRequirements } from '../../api/courts';
import { getClerkQueue, listFilings } from '../../api/filings';
import { getDemoRole } from '../../components/auth/LoginScreen';
import type { ModelContextTool } from '../types';
import { registerWorkflowTools } from './workflows';

vi.mock('../../api/cases', () => ({ getCase: vi.fn(), searchCases: vi.fn() }));
vi.mock('../../api/courts', () => ({ getFilingChecklists: vi.fn(), getFilingRequirements: vi.fn() }));
vi.mock('../../api/filings', () => ({ getClerkQueue: vi.fn(), listFilings: vi.fn() }));
vi.mock('../../components/auth/LoginScreen', () => ({
  getDemoRole: vi.fn(), getDemoCourtId: () => 3,
}));

const registered = new Map<string, ModelContextTool>();
beforeEach(async () => {
  vi.resetAllMocks();
  vi.mocked(getDemoRole).mockReturnValue('attorney');
  await registerWorkflowTools({ registerTool: async tool => { registered.set(tool.name, tool); } });
});

it('returns choices without building a filing plan for an ambiguous search', async () => {
  vi.mocked(searchCases).mockResolvedValue({
    total: 40,
    cases: [
      { id: 1, title: 'Smith A', case_number: 'A', court_id: 3 },
      { id: 2, title: 'Smith B', case_number: 'B', court_id: 4 },
    ],
  });
  const result = JSON.parse(await registered.get('attorney_motion_workflow')!.execute({
    party_name: 'Smith',
  }) as string);
  expect(result.needs_case_selection).toBe(true);
  expect(result.total).toBe(40);
  expect(result.candidates.map((c: { id: number }) => c.id)).toEqual([1, 2]);
  expect(result.filing_wizard_path).toBeUndefined();
  expect(getCase).not.toHaveBeenCalled();
  expect(getFilingRequirements).not.toHaveBeenCalled();
});

it('builds the plan for the explicitly chosen case without searching again', async () => {
  vi.mocked(getCase).mockResolvedValue({ id: 2, title: 'Smith B', case_number: 'B', court_id: 4, case_type_id: 7 });
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
  vi.mocked(getFilingChecklists).mockResolvedValue([]);
  vi.mocked(listFilings).mockResolvedValue({ total: 0, filings: [], status_counts: {}, court_names: {} });
  const result = JSON.parse(await registered.get('attorney_motion_workflow')!.execute({ case_id: 2 }) as string);
  expect(result.case.id).toBe(2);
  expect(result.filing_wizard_path).toContain('case_id=2&court_id=4&case_type_id=7');
  expect(searchCases).not.toHaveBeenCalled();
  expect(getFilingRequirements).toHaveBeenCalledWith(4, 7, 'subsequent');
});

it('prioritizes the oldest filings across both clerk statuses', async () => {
  vi.mocked(getDemoRole).mockReturnValue('clerk');
  const pending = { id: 20, submitted_at: '2026-09-04', status: 'submitted' };
  const older = { id: 10, submitted_at: '2026-09-01', status: 'under_review' };
  // Only ordering fields matter here; real queue records have additional display fields.
  vi.mocked(getClerkQueue).mockResolvedValueOnce({ total: 1, filings: [pending] } as Awaited<ReturnType<typeof getClerkQueue>>);
  vi.mocked(getClerkQueue).mockResolvedValueOnce({ total: 1, filings: [older] } as Awaited<ReturnType<typeof getClerkQueue>>);
  const result = JSON.parse(await registered.get('clerk_triage_workflow')!.execute({}) as string);
  expect(result.priority_filings.map((f: { id: number }) => f.id)).toEqual([10, 20]);
});
