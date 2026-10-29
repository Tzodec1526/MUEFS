// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { getCase, type CaseDocket } from '../../api/cases';
import { getCaseTypes, getCourt, type CaseType, type Court } from '../../api/courts';
import { CourtContext } from '../auth/CourtSession';
import { ToastProvider } from '../common/Toast';
import FilingWizard from './FilingWizard';

// Every request this test does not stub below fails instead of reaching a server.
vi.mock('../../api/client', async (importOriginal) => {
  const offline = () => Promise.reject(new Error('Unexpected API request in a component test'));
  return {
    ...await importOriginal<typeof import('../../api/client')>(),
    apiClient: { get: vi.fn(offline), post: vi.fn(offline), put: vi.fn(offline), patch: vi.fn(offline), delete: vi.fn(offline) },
  };
});
vi.mock('../../api/courts', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/courts')>(), getCourt: vi.fn(), getCaseTypes: vi.fn(),
}));
vi.mock('../../api/cases', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/cases')>(), getCase: vi.fn(),
}));

const FORGED_LINK = '/filing/new?case_id=42&court_id=3&case_type_id=11&case_title=Forged';
// What the docket's "File with Court" link opens.
const CASE_LINK = '/filing/new?case_id=42&court_id=3&case_type_id=11';

const court: Court = {
  id: 3, name: 'Third Circuit Court', county: 'Wayne', court_type: 'circuit', division: null, address: null,
  city: 'Detroit', state: 'MI', zip_code: null, phone: null, cms_type: null, is_efiling_enabled: true,
};
const civil: CaseType = {
  id: 11, court_id: 3, code: 'CZ', name: 'General Civil', category: 'civil', filing_fee_cents: 17500,
  description: null, is_active: true,
};
const docket: CaseDocket = {
  id: 42, court_id: 3, case_number: '2026-000042-CZ', case_type_id: 11, title: 'Smith v. Jones',
  can_manage_records: false, can_file: true, status: 'open', filed_date: '2026-03-02',
  filing_date: '2026-03-02', judge_id: null, participants: [], created_at: '2026-03-02T12:00:00Z',
};

function openWizard(entry: string) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[entry]}>
        <CourtContext.Provider value={{
          userId: 1, role: 'attorney', courts: [], court: undefined, loading: false,
          selectCourt: () => {}, refresh: () => {},
        }}>
          <FilingWizard />
        </CourtContext.Provider>
      </MemoryRouter>
    </ToastProvider>,
  );
}

const caption = () => screen.getByLabelText(/Case Title/) as HTMLInputElement;

beforeEach(() => {
  localStorage.setItem('demo_role', 'attorney');
  vi.mocked(getCourt).mockResolvedValue(court);
  vi.mocked(getCaseTypes).mockResolvedValue([civil]);
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  // The wizard keeps unsaved edits in sessionStorage under a key derived from the URL.
  sessionStorage.clear();
  localStorage.clear();
});

it("captions the filing with the court's case record, not the title in the link", async () => {
  vi.mocked(getCase).mockResolvedValue(docket);
  openWizard(FORGED_LINK);

  await waitFor(() => expect(caption().value).toBe('Smith v. Jones'));
  expect(getCase).toHaveBeenCalledWith(42);
  expect(screen.getByText('Filing motion to:').parentElement?.textContent).toBe('Filing motion to: Smith v. Jones');
  expect(screen.queryByText(/Forged/)).toBeNull();
});

it('leaves the caption blank rather than trusting the link when the case record cannot load', async () => {
  vi.mocked(getCase).mockRejectedValue(new Error('Network Error'));
  openWizard(FORGED_LINK);

  // The court name arrives in the same update that would have set the caption.
  await screen.findByText('Third Circuit Court');
  expect(caption().value).toBe('');
  expect(screen.queryByText(/Forged/)).toBeNull();
});

it('offers a retry when the case record fails to load, and retrying fills in the caption', async () => {
  vi.mocked(getCase).mockRejectedValueOnce(new Error('Network Error')).mockResolvedValueOnce(docket);
  openWizard(CASE_LINK);

  await screen.findByText(/couldn't load the court's record for this case/);
  expect((screen.getByRole('button', { name: 'Save draft' }) as HTMLButtonElement).disabled).toBe(true);
  // Continue explains the read-only caption instead of asking for a title the filer cannot type.
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
  expect(await screen.findByText(/The case title comes from the court's case record/)).toBeTruthy();
  expect(screen.queryByText('Please enter a case title to continue.')).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

  await waitFor(() => expect(caption().value).toBe('Smith v. Jones'));
  expect(getCase).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
  expect(screen.queryByText(/The case title comes from the court's case record/)).toBeNull();
  expect((screen.getByRole('button', { name: 'Save draft' }) as HTMLButtonElement).disabled).toBe(false);
});

it("names the existing case's type even after the court closed that type to new cases", async () => {
  const closedToNewCases = { ...civil, is_active: false };
  vi.mocked(getCaseTypes).mockImplementation(async (_court, includeInactive) => includeInactive ? [closedToNewCases] : []);
  vi.mocked(getCase).mockResolvedValue(docket);
  openWizard(CASE_LINK);

  expect(await screen.findByText('General Civil')).toBeTruthy();
});

it('groups the File with Court and Service Only choices as one named radio group', async () => {
  vi.mocked(getCase).mockResolvedValue(docket);
  openWizard(CASE_LINK);

  const group = await screen.findByRole('group', { name: /Filing Type/ });
  expect(within(group).getAllByRole('radio').map(radio => radio.getAttribute('value')))
    .toEqual(['subsequent', 'service_only']);
  expect(document.querySelector('label[for="filingType"]')).toBeNull();
});

it("keeps a self-represented filer's choice to turn plain-language guidance off", async () => {
  localStorage.setItem('demo_role', 'srl');
  vi.mocked(getCase).mockResolvedValue(docket);
  const guidance = () => screen.getByLabelText('Plain-language guidance') as HTMLInputElement;
  const first = openWizard(CASE_LINK);
  // Plain language is the default for a self-represented filer who has not chosen.
  expect(guidance().checked).toBe(true);
  fireEvent.click(guidance());
  expect(guidance().checked).toBe(false);
  await screen.findByText('Filing motion to:');
  first.unmount();

  openWizard(CASE_LINK);

  expect(guidance().checked).toBe(false);
  // Let the reopened wizard (which restores the unsaved draft) finish loading.
  await screen.findByText('Third Circuit Court');
});
