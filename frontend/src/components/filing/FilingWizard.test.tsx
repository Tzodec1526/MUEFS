import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { Link, MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AxiosError, type AxiosResponse } from 'axios';
import { getCase, searchCases, type CaseDocket, type CaseSearchResult } from '../../api/cases';
import {
  getCaseTypes, getCourt, getFilingRequirements, listCourts, type CaseType, type Court,
} from '../../api/courts';
import { getFilingFees, type FilingFees } from '../../api/documents';
import {
  createFiling, getFiling, submitFiling, updateFiling, validateFiling, type FilingEnvelope,
} from '../../api/filings';
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
  listCourts: vi.fn(), getFilingRequirements: vi.fn(),
}));
vi.mock('../../api/filings', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/filings')>(),
  createFiling: vi.fn(), getFiling: vi.fn(), updateFiling: vi.fn(), validateFiling: vi.fn(), submitFiling: vi.fn(),
}));
vi.mock('../../api/documents', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/documents')>(), getFilingFees: vi.fn(),
}));
vi.mock('../../api/cases', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/cases')>(), getCase: vi.fn(), searchCases: vi.fn(),
}));

const FORGED_LINK = '/filing/new?case_id=42&court_id=3&case_type_id=11&case_title=Forged';
// What the docket's "File in this case" link opens.
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
          userId: 1, role: localStorage.getItem('demo_role'), courts: [], court: undefined, loading: false,
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
  vi.mocked(listCourts).mockRejectedValue(new Error('Unexpected API request in a component test'));
  vi.mocked(getFilingRequirements).mockRejectedValue(new Error('Unexpected API request in a component test'));
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
  expect(screen.getByText('Case:').parentElement?.textContent).toBe('Case: Smith v. Jones');
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

it('heads a filing in an existing case with its case number and does not call it a motion', async () => {
  vi.mocked(getCase).mockResolvedValue(docket);
  openWizard(CASE_LINK);

  expect(await screen.findByText('Case 2026-000042-CZ')).toBeTruthy();
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('File in an existing case');
  expect(document.body.textContent).not.toMatch(/motion/i);
  expect((screen.getByRole('textbox', { name: /Filing Description/ }) as HTMLTextAreaElement).placeholder).not.toMatch(/motion/i);
});

async function pickExistingCase() {
  const found = { id: 42, case_number: '2026-000042-CZ', title: 'Smith v. Jones', case_type_id: 11, status: 'open' } as CaseSearchResult;
  vi.mocked(searchCases).mockResolvedValue({ cases: [found], total: 1, page: 1, page_size: 25 });
  fireEvent.click(await screen.findByRole('button', { name: /File in an existing case/ }));
  fireEvent.change(screen.getByLabelText('Case number or party name'), { target: { value: 'Smith' } });
  fireEvent.click(button('Search'));
  fireEvent.click(await screen.findByRole('button', { name: 'Select' }));
}

it('takes the case number from the case the filer picks', async () => {
  serveCourtsAndTypes();
  openWizard('/filing/new?court_id=3');
  await pickExistingCase();

  fireEvent.click(button('Continue'));

  await screen.findByRole('heading', { name: 'Filing Details' });
  expect(screen.getByText('Case 2026-000042-CZ')).toBeTruthy();
});

it('forgets the case number when the filer switches to a new case', async () => {
  serveCourtsAndTypes();
  openWizard('/filing/new?court_id=3');
  await pickExistingCase();
  await screen.findByText('Case 2026-000042-CZ');

  fireEvent.click(screen.getByRole('button', { name: /Start a new case/ }));

  expect(screen.queryByText('Case 2026-000042-CZ')).toBeNull();
});

it('shows the case number of a saved filing in an existing case', async () => {
  vi.mocked(getFiling).mockResolvedValue(savedFiling({ case_id: 42, filing_type: 'subsequent' }));
  vi.mocked(getCase).mockResolvedValue(docket);
  openWizard('/filing/new?filing_id=7&step=details');

  expect(await screen.findByText('Case 2026-000042-CZ')).toBeTruthy();
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Continue Filing #7');
});

it('reports once that the case number of a saved filing could not load, and still opens the filing', async () => {
  vi.mocked(getFiling).mockResolvedValue(savedFiling({ case_id: 42, filing_type: 'subsequent' }));
  vi.mocked(getCase).mockRejectedValue(new Error('Network Error'));
  openWizard('/filing/new?filing_id=7&step=details');

  expect(await screen.findAllByText('Could not load the case number.')).toHaveLength(1);
  expect(caption().value).toBe('Doe v. Roe');
  expect(screen.queryByText(/^Case \d/)).toBeNull();
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
  await screen.findByText('Smith v. Jones');
  first.unmount();

  openWizard(CASE_LINK);

  expect(guidance().checked).toBe(false);
  // Let the reopened wizard (which restores the unsaved draft) finish loading.
  await screen.findByText('Third Circuit Court');
});

const SAVED_TOKEN = 'a'.repeat(64);
const LATEST_TOKEN = 'b'.repeat(64);

function savedFiling(overrides: Partial<FilingEnvelope> = {}): FilingEnvelope {
  return {
    id: 7, court_id: 3, case_id: null, case_type_id: 11, filer_id: 1, filing_type: 'initial', status: 'draft',
    payment_id: null, case_title: 'Doe v. Roe', filing_description: 'Complaint for breach of contract',
    submitted_at: null, reviewed_at: null, rejection_reason: null, fee_waiver_requested: false,
    fee_waiver_granted: null, fee_waiver_reason: null, fee_waiver_referred_at: null, fee_waiver_decided_at: null,
    fee_waiver_amount_due_cents: null, documents: [], created_at: '2026-09-28T12:00:00Z',
    updated_at: '2026-09-28T12:00:00Z', submission_count: 0, filing_date: null, filing_date_basis: null,
    submission_token: 's-7', details_token: SAVED_TOKEN, ...overrides,
  };
}

const complaint = {
  id: 70, document_type_code: 'COMPLAINT', title: 'Complaint', file_size_bytes: 2048, mime_type: 'application/pdf',
  page_count: 3, sha256_hash: 'c'.repeat(64), is_confidential: false, is_text_searchable: true,
  uploaded_at: '2026-09-28T12:00:00Z',
};

function paidFees(filing: FilingEnvelope): FilingFees & { filing: FilingEnvelope } {
  return {
    filing_id: filing.id, version: 1, payment_version: 1, source: 'demo', assessment_id: null,
    authority_reference: null, items: [], total_cents: 17500, paid_cents: 17500, balance_due_cents: 0,
    overpaid_cents: 0, review_requested_at: null, review_reason: null, assessment_stale: false,
    can_request_review: false, can_assess: false, can_pay: false, can_request_waiver: false, obligation_met: true,
    payments_simulated: true, can_manage_external_payments: false, can_record_external_payment: false, filing,
  };
}

function conflictError(): AxiosError {
  return new AxiosError('Request failed with status code 409', 'ERR_BAD_REQUEST', undefined, undefined,
    { status: 409, data: { detail: 'This filing changed since you opened it.' } } as AxiosResponse);
}

const stepButton = (label: string) => within(screen.getByRole('navigation', { name: 'Filing progress' }))
  .getByRole('button', { name: new RegExp(`(^|[\\d✓\\s])${label}$`) }) as HTMLButtonElement;
const button = (name: string | RegExp) => screen.getByRole('button', { name }) as HTMLButtonElement;
const descriptionField = () => screen.getByLabelText(/Filing Description/) as HTMLTextAreaElement;

async function stepError(message: string) {
  expect((await screen.findByRole('alert')).textContent).toBe(message);
}

function serveCourtsAndTypes() {
  vi.mocked(listCourts).mockImplementation(async (params) =>
    params?.tier === 'trial' ? { courts: [court], total: 1 } : { courts: [], total: 0 });
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
}

async function chooseNewCaseAndType() {
  fireEvent.click(await screen.findByRole('button', { name: /Start a new case/ }));
  fireEvent.click(button('Continue'));
  fireEvent.click(await screen.findByRole('radio', { name: /General Civil/ }));
  fireEvent.click(button('Continue'));
  await screen.findByRole('heading', { name: 'Case Details' });
}

it('walks a new case through each step, refusing to advance past an unfinished one', async () => {
  serveCourtsAndTypes();
  openWizard('/filing/new');

  expect(stepButton('Court').getAttribute('aria-current')).toBe('step');
  expect(['Case', 'Case type', 'Details', 'Documents', 'Review'].map(label => stepButton(label).disabled))
    .toEqual([true, true, true, true, true]);
  expect(button('Back').disabled).toBe(true);
  fireEvent.click(button('Continue'));
  await stepError('Please select a court to continue.');

  fireEvent.click(await screen.findByRole('button', { name: 'Third Circuit Court' }));
  fireEvent.click(button('Continue'));
  await screen.findByRole('heading', { name: 'Existing case or new case?' });
  expect(stepButton('Case').getAttribute('aria-current')).toBe('step');
  expect(screen.queryByRole('alert')).toBeNull();
  fireEvent.click(button('Continue'));
  await stepError('Please choose an existing case or start a new case.');

  fireEvent.click(screen.getByRole('button', { name: /Start a new case/ }));
  fireEvent.click(button('Continue'));
  await screen.findByRole('heading', { name: 'Select Case Type & Review Requirements' });
  fireEvent.click(button('Continue'));
  await stepError('Please select a case type to continue.');

  fireEvent.click(await screen.findByRole('radio', { name: /General Civil/ }));
  fireEvent.click(button('Continue'));
  await screen.findByRole('heading', { name: 'Case Details' });
  fireEvent.click(button('Continue'));
  await stepError('Please enter a case title to continue.');
  expect(createFiling).not.toHaveBeenCalled();
  expect([stepButton('Documents').disabled, stepButton('Review').disabled]).toEqual([true, true]);
});

it('clears a step error as soon as the filer fixes the field it names', async () => {
  serveCourtsAndTypes();
  openWizard('/filing/new');

  fireEvent.click(button('Continue'));
  await stepError('Please select a court to continue.');
  fireEvent.click(await screen.findByRole('button', { name: 'Third Circuit Court' }));
  expect(screen.queryByRole('alert')).toBeNull();

  fireEvent.click(button('Continue'));
  await screen.findByRole('heading', { name: 'Existing case or new case?' });
  fireEvent.click(button('Continue'));
  await stepError('Please choose an existing case or start a new case.');
  fireEvent.click(screen.getByRole('button', { name: /Start a new case/ }));
  expect(screen.queryByRole('alert')).toBeNull();

  fireEvent.click(button('Continue'));
  fireEvent.click(await screen.findByRole('radio', { name: /General Civil/ }));
  fireEvent.click(button('Continue'));
  await screen.findByRole('heading', { name: 'Case Details' });
  fireEvent.click(button('Continue'));
  await stepError('Please enter a case title to continue.');
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe' } });
  expect(screen.queryByRole('alert')).toBeNull();
});

it('keeps a failed save on screen while the filer edits, until the next save attempt', async () => {
  serveCourtsAndTypes();
  vi.mocked(createFiling).mockRejectedValueOnce({ response: { status: 429, data: {} } });
  openWizard('/filing/new?court_id=3');
  await chooseNewCaseAndType();
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe' } });
  fireEvent.click(button('Save draft'));
  await stepError('Too many requests. Please wait a moment and try again.');

  fireEvent.change(descriptionField(), { target: { value: 'Complaint for breach of contract' } });
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe Corp.' } });

  expect(screen.getByRole('alert').textContent).toBe('Too many requests. Please wait a moment and try again.');
  vi.mocked(createFiling).mockReturnValueOnce(new Promise(() => {}));
  fireEvent.click(button('Save draft'));
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
});

it('moves focus to the error after a failed save', async () => {
  vi.mocked(getFiling).mockResolvedValue(savedFiling());
  vi.mocked(updateFiling).mockRejectedValueOnce({ response: { status: 429, data: {} } });
  openWizard('/filing/new?filing_id=7&step=details');
  await waitFor(() => expect(caption().value).toBe('Doe v. Roe'));
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe, amended' } });

  fireEvent.click(button('Save draft'));

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toBe('Too many requests. Please wait a moment and try again.');
  expect(document.activeElement).toBe(alert);
});

it('keeps focus where it is when a step error appears', async () => {
  serveCourtsAndTypes();
  openWizard('/filing/new');
  const next = button('Continue');
  next.focus();

  fireEvent.click(next);

  await stepError('Please select a court to continue.');
  expect(document.activeElement).toBe(next);
});

it('keeps a save failure on its own step until the filer leaves that step', async () => {
  vi.mocked(getFiling).mockResolvedValue(savedFiling());
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
  vi.mocked(updateFiling).mockRejectedValueOnce({ response: { status: 429, data: {} } });
  render(
    <ToastProvider>
      <MemoryRouter initialEntries={['/filing/new?filing_id=7&step=details']}>
        <Link to="/filing/new?filing_id=7">Open the documents step</Link>
        <CourtContext.Provider value={{
          userId: 1, role: 'attorney', courts: [], court: undefined, loading: false, selectCourt: () => {}, refresh: () => {},
        }}>
          <FilingWizard />
        </CourtContext.Provider>
      </MemoryRouter>
    </ToastProvider>,
  );
  await waitFor(() => expect(caption().value).toBe('Doe v. Roe'));
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe, amended' } });
  fireEvent.click(button('Save draft'));
  await screen.findByRole('alert');

  fireEvent.click(stepButton('Details'));
  expect(screen.getByRole('alert').textContent).toBe('Too many requests. Please wait a moment and try again.');

  fireEvent.click(screen.getByRole('link', { name: 'Open the documents step' }));

  await screen.findByRole('heading', { name: 'Upload Documents' });
  expect(screen.queryByRole('alert')).toBeNull();

  fireEvent.click(button('Back'));

  await waitFor(() => expect(caption().value).toBe('Doe v. Roe'));
  expect(screen.queryByRole('alert')).toBeNull();
});

it('offers no way off the details step while a first save has failed', async () => {
  serveCourtsAndTypes();
  vi.mocked(createFiling).mockRejectedValueOnce({ response: { status: 429, data: {} } });
  openWizard('/filing/new?court_id=3');
  await chooseNewCaseAndType();
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe' } });

  fireEvent.click(button('Save draft'));
  await screen.findByRole('alert');

  expect([button('Back').disabled, stepButton('Case type').disabled]).toEqual([true, true]);
});

it('shows the unsaved-changes note only on the step that can save, and does not announce it', async () => {
  serveCourtsAndTypes();
  openWizard('/filing/new?court_id=3');
  await screen.findByRole('heading', { name: 'Existing case or new case?' });
  expect(screen.queryByText(/Unsaved changes/)).toBeNull();

  await chooseNewCaseAndType();

  expect(screen.getByText(/Unsaved changes/).closest('[role],[aria-live]')).toBeNull();
  expect(button('Save draft')).toBeTruthy();

  fireEvent.click(button('Back'));

  await screen.findByRole('heading', { name: 'Select Case Type & Review Requirements' });
  expect(screen.queryByText(/Unsaved changes/)).toBeNull();
});

const stepLabels = () => within(screen.getByRole('navigation', { name: 'Filing progress' }))
  .getAllByRole('button').map(step => step.querySelector('.step-label')?.textContent);

it('names each step of a new case in a word or two', async () => {
  serveCourtsAndTypes();
  openWizard('/filing/new');

  expect(stepLabels()).toEqual(['Court', 'Case', 'Case type', 'Details', 'Documents', 'Review']);
});

it('keeps the plain-language step names just as short', async () => {
  localStorage.setItem('demo_role', 'srl');
  serveCourtsAndTypes();
  openWizard('/filing/new');

  expect(stepLabels()).toEqual(['Your court', 'Your case', 'Kind of case', 'Your filing', 'Your papers', 'Check and send']);
  await screen.findByRole('button', { name: 'Third Circuit Court' });
});

it('skips the case type step for a filing in an existing case', async () => {
  vi.mocked(getCase).mockResolvedValue(docket);
  openWizard(CASE_LINK);

  expect(stepLabels()).toEqual(['Court', 'Case', 'Details', 'Documents', 'Review']);
  await screen.findByText('Third Circuit Court');
});

const headingLevels = () => screen.getAllByRole('heading').map(heading => Number(heading.tagName[1]));

function expectNoSkippedHeadingLevels() {
  const levels = headingLevels();
  expect(levels[0]).toBe(1);
  expect(levels.filter((level, index) => index > 0 && level > levels[index - 1] + 1)).toEqual([]);
}

it('steps down one heading level at a time on the court, case and case type steps', async () => {
  serveCourtsAndTypes();
  openWizard('/filing/new');
  await screen.findByRole('button', { name: 'Third Circuit Court' });
  expectNoSkippedHeadingLevels();

  fireEvent.click(screen.getByRole('button', { name: 'Third Circuit Court' }));
  fireEvent.click(button('Continue'));
  await screen.findByRole('heading', { name: 'Existing case or new case?' });
  expectNoSkippedHeadingLevels();

  fireEvent.click(screen.getByRole('button', { name: /Start a new case/ }));
  fireEvent.click(button('Continue'));
  vi.mocked(getFilingRequirements).mockResolvedValue([{
    id: 1, document_type_code: 'COMPLAINT', is_required: true, description: 'Complaint', mcr_reference: null,
    local_rule_reference: null, page_limit: null, format_notes: null,
  }]);
  fireEvent.click(await screen.findByRole('radio', { name: /General Civil/ }));
  await screen.findByRole('heading', { name: 'Required documents (1)' });
  expectNoSkippedHeadingLevels();
});

it('steps down one heading level at a time on the documents and review steps', async () => {
  const draft = savedFiling({ documents: [complaint] });
  vi.mocked(getFiling).mockResolvedValue(draft);
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
  vi.mocked(validateFiling).mockResolvedValue({
    is_valid: false, errors: ['A summons is required.'], warnings: ['Check the caption.'], missing_required_documents: ['Summons'],
  });
  vi.mocked(getFilingFees).mockResolvedValue(paidFees(draft));
  openWizard('/filing/new?filing_id=7');
  await screen.findByRole('heading', { name: 'Upload Documents' });
  expectNoSkippedHeadingLevels();

  fireEvent.click(button('Review Filing'));

  await screen.findByRole('heading', { name: 'Issues Found' });
  await screen.findByText('No additional payment is required for the current filing.');
  expectNoSkippedHeadingLevels();
});

it('steps down one heading level at a time in the conflict comparison', async () => {
  await openConflict();

  expectNoSkippedHeadingLevels();
});

it('returns to a completed step from the progress bar, and back one step with Back', async () => {
  serveCourtsAndTypes();
  openWizard('/filing/new?court_id=3');
  await chooseNewCaseAndType();

  fireEvent.click(button('Back'));
  await screen.findByRole('heading', { name: 'Select Case Type & Review Requirements' });

  fireEvent.click(stepButton('Court'));

  expect(await screen.findByRole('heading', { name: 'Select Court', level: 2 })).toBeTruthy();
  expect(stepButton('Court').getAttribute('aria-current')).toBe('step');
  expect(stepButton('Case').disabled).toBe(true);
});

it('saves a new filing as a draft and locks the court and case choices', async () => {
  serveCourtsAndTypes();
  const created = savedFiling();
  vi.mocked(createFiling).mockResolvedValue(created);
  vi.mocked(getFiling).mockResolvedValue(created);
  openWizard('/filing/new?court_id=3');
  await chooseNewCaseAndType();
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe' } });
  fireEvent.change(descriptionField(), { target: { value: 'Complaint for breach of contract' } });

  fireEvent.click(button('Save draft'));

  await screen.findByRole('heading', { name: 'Continue Filing #7' });
  expect(createFiling).toHaveBeenCalledTimes(1);
  const [payload, creationKey] = vi.mocked(createFiling).mock.calls[0];
  expect(payload).toEqual({
    court_id: 3, case_id: undefined, case_type_id: 11, filing_type: 'initial',
    case_title: 'Doe v. Roe', filing_description: 'Complaint for breach of contract',
  });
  expect(creationKey).toMatch(/^[0-9a-f-]{36}$/);
  await waitFor(() => expect(caption().value).toBe('Doe v. Roe'));
  expect([stepButton('Court').disabled, stepButton('Case type').disabled, button('Back').disabled])
    .toEqual([true, true, true]);
});

it('saves the details and moves on to documents when the filer continues', async () => {
  serveCourtsAndTypes();
  const created = savedFiling();
  vi.mocked(createFiling).mockResolvedValue(created);
  vi.mocked(getFiling).mockResolvedValue(created);
  openWizard('/filing/new?court_id=3');
  await chooseNewCaseAndType();
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe' } });

  fireEvent.click(button('Continue'));

  expect(await screen.findByRole('heading', { name: 'Upload Documents' })).toBeTruthy();
  expect(createFiling).toHaveBeenCalledTimes(1);
  expect(stepButton('Documents').getAttribute('aria-current')).toBe('step');
  fireEvent.click(button('Review Filing'));
  await stepError('Please upload at least one document to continue.');
});

it('offers unsaved edits from this tab when a new filing is reopened', async () => {
  serveCourtsAndTypes();
  const first = openWizard('/filing/new?court_id=3');
  await chooseNewCaseAndType();
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe' } });
  first.unmount();

  openWizard('/filing/new?court_id=3');

  expect(await screen.findByText('Recovered unsaved edits from this tab. Save them to your account before closing the tab.'))
    .toBeTruthy();
  expect(screen.getByText('Case:').parentElement?.textContent).toBe('Case: Doe v. Roe');
  expect(screen.getByText('Type:').parentElement?.textContent).toBe('Type: General Civil');

  fireEvent.click(button('Continue Editing'));

  expect(screen.queryByText(/Recovered unsaved edits/)).toBeNull();
  expect(screen.getByText('Case:').parentElement?.textContent).toBe('Case: Doe v. Roe');
});

it('discards recovered edits when the filer starts fresh', async () => {
  serveCourtsAndTypes();
  const first = openWizard('/filing/new?court_id=3');
  await chooseNewCaseAndType();
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe' } });
  first.unmount();
  const second = openWizard('/filing/new?court_id=3');
  await screen.findByText(/Recovered unsaved edits/);

  fireEvent.click(button('Start Fresh'));

  expect(screen.queryByText(/Recovered unsaved edits/)).toBeNull();
  expect(screen.queryByText('Case:')).toBeNull();
  expect(stepButton('Court').getAttribute('aria-current')).toBe('step');
  second.unmount();

  openWizard('/filing/new?court_id=3');

  await screen.findByRole('heading', { name: 'Existing case or new case?' });
  expect(screen.queryByText(/Recovered unsaved edits/)).toBeNull();
});

it('recovers unsaved edits to a saved filing, and can return to the saved details', async () => {
  vi.mocked(getFiling).mockResolvedValue(savedFiling());
  const first = openWizard('/filing/new?filing_id=7&step=details');
  await waitFor(() => expect(caption().value).toBe('Doe v. Roe'));
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe, amended' } });
  first.unmount();

  openWizard('/filing/new?filing_id=7&step=details');

  await screen.findByText(/Recovered unsaved edits/);
  expect(caption().value).toBe('Doe v. Roe, amended');

  fireEvent.click(button('Use Saved Details'));

  expect(caption().value).toBe('Doe v. Roe');
  expect(screen.queryByText(/Recovered unsaved edits/)).toBeNull();
});

it('saves edits to a saved filing against the version it loaded', async () => {
  vi.mocked(getFiling).mockResolvedValue(savedFiling());
  vi.mocked(updateFiling).mockResolvedValue(savedFiling({ case_title: 'Doe v. Roe, amended', details_token: LATEST_TOKEN }));
  openWizard('/filing/new?filing_id=7&step=details');
  await waitFor(() => expect(caption().value).toBe('Doe v. Roe'));
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe, amended' } });

  fireEvent.click(button('Save draft'));

  await screen.findByText('Draft saved to your account. You can continue it from My Filings.');
  expect(updateFiling).toHaveBeenCalledWith(7, {
    expected_details_token: SAVED_TOKEN, case_title: 'Doe v. Roe, amended',
    filing_description: 'Complaint for breach of contract',
  });
  expect(createFiling).not.toHaveBeenCalled();
});

it('saves edits to a saved filing and moves on to documents when the filer continues', async () => {
  vi.mocked(getFiling).mockResolvedValue(savedFiling());
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
  vi.mocked(updateFiling).mockResolvedValue(savedFiling({ case_title: 'Doe v. Roe, amended', details_token: LATEST_TOKEN }));
  openWizard('/filing/new?filing_id=7&step=details');
  await waitFor(() => expect(caption().value).toBe('Doe v. Roe'));
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe, amended' } });

  fireEvent.click(button('Continue'));

  expect(await screen.findByRole('heading', { name: 'Upload Documents' })).toBeTruthy();
  expect(updateFiling).toHaveBeenCalledTimes(1);
  expect(stepButton('Documents').getAttribute('aria-current')).toBe('step');
});

async function openConflict() {
  const latest = savedFiling({ case_title: 'Doe v. Roe, Inc.', filing_description: 'Amended complaint', details_token: LATEST_TOKEN });
  vi.mocked(getFiling).mockResolvedValueOnce(savedFiling()).mockResolvedValue(latest);
  vi.mocked(updateFiling).mockRejectedValueOnce(conflictError());
  openWizard('/filing/new?filing_id=7&step=details');
  await waitFor(() => expect(caption().value).toBe('Doe v. Roe'));
  fireEvent.change(caption(), { target: { value: 'Doe v. Roe, amended' } });
  fireEvent.click(button('Save draft'));
  return screen.findByRole('heading', { name: 'Compare changes before saving' });
}

it('compares the edits with the saved filing when someone else saved it first', async () => {
  const heading = await openConflict();

  const comparison = screen.getByRole('region', { name: 'Compare changes before saving' });
  expect(within(comparison).getByText('Doe v. Roe, amended')).toBeTruthy();
  expect(within(comparison).getByText('Doe v. Roe, Inc.')).toBeTruthy();
  expect(within(comparison).getByText('Amended complaint')).toBeTruthy();
  expect(document.activeElement).toBe(heading);
  expect([button('Save draft').disabled, button('Continue').disabled]).toEqual([true, true]);
  expect(getFiling).toHaveBeenCalledTimes(2);
});

it('keeps the edits after a conflict and saves them against the latest version', async () => {
  await openConflict();
  vi.mocked(updateFiling).mockResolvedValue(savedFiling({ case_title: 'Doe v. Roe, amended', details_token: 'd'.repeat(64) }));

  fireEvent.click(button('Keep my edits for next save'));

  expect(screen.getByText('Your edits are ready. Save draft or Continue to save them to your account.')).toBeTruthy();
  expect(screen.queryByRole('heading', { name: 'Compare changes before saving' })).toBeNull();
  expect(caption().value).toBe('Doe v. Roe, amended');

  fireEvent.click(button('Save draft'));

  await screen.findByText('Draft saved to your account. You can continue it from My Filings.');
  expect(vi.mocked(updateFiling).mock.lastCall).toEqual([7, {
    expected_details_token: LATEST_TOKEN, case_title: 'Doe v. Roe, amended',
    filing_description: 'Complaint for breach of contract',
  }]);
});

it('replaces the edits with the saved details after a conflict when the filer chooses them', async () => {
  await openConflict();

  fireEvent.click(button('Use saved details'));

  expect(screen.getByText('Showing the saved details.')).toBeTruthy();
  expect(screen.queryByRole('heading', { name: 'Compare changes before saving' })).toBeNull();
  expect(caption().value).toBe('Doe v. Roe, Inc.');
  expect(descriptionField().value).toBe('Amended complaint');
});

it('submits a valid, paid filing from the review step', async () => {
  const draft = savedFiling({ documents: [complaint] });
  vi.mocked(getFiling).mockResolvedValue(draft);
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
  vi.mocked(validateFiling).mockResolvedValue({ is_valid: true, errors: [], warnings: [], missing_required_documents: [] });
  vi.mocked(getFilingFees).mockResolvedValue(paidFees(draft));
  vi.mocked(submitFiling).mockResolvedValue({ ...draft, status: 'submitted', submission_count: 1 });
  openWizard('/filing/new?filing_id=7');
  await screen.findByRole('heading', { name: 'Upload Documents' });

  fireEvent.click(button('Review Filing'));

  await screen.findByRole('heading', { name: 'Review Your Filing' });
  const submit = await screen.findByRole('button', { name: 'Submit Filing' }) as HTMLButtonElement;
  await waitFor(() => expect(submit.disabled).toBe(false));

  fireEvent.click(submit);

  expect(await screen.findByRole('heading', { name: 'Filing Submitted Successfully' })).toBeTruthy();
  expect(submitFiling).toHaveBeenCalledTimes(1);
  const [filingId, token, idempotencyKey] = vi.mocked(submitFiling).mock.calls[0];
  expect([filingId, token]).toEqual([7, 's-7']);
  expect(idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
  expect(screen.queryByRole('button', { name: 'Back' })).toBeNull();
});

it('does not submit a filing that fails validation', async () => {
  const draft = savedFiling({ documents: [complaint] });
  vi.mocked(getFiling).mockResolvedValue(draft);
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
  vi.mocked(validateFiling).mockResolvedValue({
    is_valid: false, errors: ['A summons is required.'], warnings: [], missing_required_documents: ['Summons'],
  });
  vi.mocked(getFilingFees).mockResolvedValue(paidFees(draft));
  openWizard('/filing/new?filing_id=7');
  fireEvent.click(await screen.findByRole('button', { name: 'Review Filing' }));

  expect(await screen.findByText('A summons is required.')).toBeTruthy();
  await screen.findByText('No additional payment is required for the current filing.');
  expect(button('Submit Filing').disabled).toBe(true);
  expect(submitFiling).not.toHaveBeenCalled();
});

it('shows a saved filing that fails to load inline and loads it again on retry', async () => {
  vi.mocked(getFiling).mockRejectedValueOnce(new Error('Network Error')).mockResolvedValue(savedFiling());
  openWizard('/filing/new?filing_id=7&step=details');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Could not load this filing. Please retry.');

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  await waitFor(() => expect(caption().value).toBe('Doe v. Roe'));
  expect(getFiling).toHaveBeenCalledTimes(2);
});

it("reports once that the court's name could not load for a filing link", async () => {
  vi.mocked(getCase).mockResolvedValue(docket);
  vi.mocked(getCourt).mockRejectedValue(new Error('Network Error'));
  openWizard(CASE_LINK);

  expect(await screen.findAllByText("Could not load the court's name.")).toHaveLength(1);
  expect(screen.getByText('Court #3')).toBeTruthy();
});

it('reports once that the case type name could not load for a filing link', async () => {
  vi.mocked(getCase).mockResolvedValue(docket);
  vi.mocked(getCaseTypes).mockRejectedValue(new Error('Network Error'));
  openWizard(CASE_LINK);

  expect(await screen.findAllByText('Could not load the case type name.')).toHaveLength(1);
  expect(screen.getByText('Third Circuit Court')).toBeTruthy();
});
