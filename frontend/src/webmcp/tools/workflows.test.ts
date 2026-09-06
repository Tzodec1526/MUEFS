import { beforeEach, expect, it, vi } from 'vitest';
import { getCase, searchCases } from '../../api/cases';
import { getFilingChecklists, getFilingRequirements } from '../../api/courts';
import { getFilingStatusCounts } from '../../api/filings';
import { getDemoRole } from '../../components/auth/LoginScreen';
import type { ModelContextTool } from '../types';
import { registerWorkflowTools } from './workflows';

vi.mock('../../api/cases', () => ({ getCase: vi.fn(), searchCases: vi.fn() }));
vi.mock('../../api/courts', () => ({ getFilingChecklists: vi.fn(), getFilingRequirements: vi.fn() }));
vi.mock('../../api/filings', () => ({ getClerkQueue: vi.fn(), getFilingStatusCounts: vi.fn() }));
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
  vi.mocked(getFilingStatusCounts).mockResolvedValue({ draft: 7, accepted: 20 });
  const result = JSON.parse(await registered.get('attorney_motion_workflow')!.execute({ case_id: 2 }) as string);
  expect(result.case.id).toBe(2);
  expect(result.draft_filings_pending).toBe(7);
  expect(result.filing_wizard_path).toContain('case_id=2&court_id=4&case_type_id=7');
  expect(searchCases).not.toHaveBeenCalled();
  expect(getFilingRequirements).toHaveBeenCalledWith(4, 7, 'subsequent');
});
