import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { searchCases, type CaseSearchResult } from '../../api/cases';
import { getCaseTypes, type CaseType } from '../../api/courts';
import { ToastProvider } from '../common/Toast';
import CaseSelector from './CaseSelector';

vi.mock('../../api/cases', () => ({ searchCases: vi.fn() }));
vi.mock('../../api/courts', () => ({ getCaseTypes: vi.fn() }));

const closedToNewCases: CaseType = {
  id: 11, court_id: 3, code: 'CZ', name: 'General Civil', category: 'civil', filing_fee_cents: 17500,
  description: null, is_active: false,
};

const smithCase: CaseSearchResult = {
  id: 42, case_number: '2026-000042-CZ', case_type_id: 11, title: 'Smith v. Jones', status: 'open',
  court_id: 3, court_name: 'Third Circuit Court', court_county: 'Wayne', filed_date: '2026-03-02',
  filing_date: '2026-03-02', participants: [],
};

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("carries an existing case's type name even after the court closed that type to new cases", async () => {
  // Like the API: types closed to new cases are listed only when a caller asks for them.
  vi.mocked(getCaseTypes).mockImplementation(async (_court, includeInactive = false) =>
    [closedToNewCases].filter(type => includeInactive || type.is_active));
  vi.mocked(searchCases).mockResolvedValue({ cases: [smithCase], total: 1, page: 1, page_size: 25 });
  const onSelectExisting = vi.fn();
  render(<CaseSelector courtId={3} courtName="Third Circuit Court" selectedCaseId={null} isNewChosen={false}
    onChooseExisting={vi.fn()} onSelectExisting={onSelectExisting} onSelectNew={vi.fn()} />);
  await waitFor(() => expect(getCaseTypes).toHaveBeenCalled());

  fireEvent.click(screen.getByRole('button', { name: /File in an existing case/ }));
  fireEvent.change(screen.getByLabelText('Case number or party name'), { target: { value: 'Smith' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Select' }));

  expect(onSelectExisting).toHaveBeenCalledWith(smithCase, 'General Civil');
});

it('reports once that the case type names could not load', async () => {
  vi.mocked(getCaseTypes).mockRejectedValue(new Error('Network Error'));
  render(<ToastProvider><CaseSelector courtId={3} courtName="Third Circuit Court" selectedCaseId={null} isNewChosen={false}
    onChooseExisting={vi.fn()} onSelectExisting={vi.fn()} onSelectNew={vi.fn()} /></ToastProvider>);

  expect(await screen.findAllByText('Could not load the case type names.')).toHaveLength(1);
});
