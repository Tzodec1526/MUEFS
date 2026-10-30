import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { getFilingRequirements, type FilingRequirement } from '../../api/courts';
import DocumentUpload from './DocumentUpload';

vi.mock('../../api/courts', () => ({ getFilingRequirements: vi.fn() }));
vi.mock('../../api/filings', () => ({ getFiling: vi.fn(), uploadDocument: vi.fn(), removeDocument: vi.fn() }));

const COURT_GROUP = "Listed in this court's rules";

function requirement(id: number, code: string, description: string, mcr: string): FilingRequirement {
  return {
    id, document_type_code: code, is_required: true, description, mcr_reference: mcr,
    local_rule_reference: null, page_limit: null, format_notes: null,
  };
}

// BUS_CT_NOTICE is not in the built-in catalog; COMPLAINT is.
const COURT_RULE_TYPES = [
  requirement(1, 'BUS_CT_NOTICE', 'Business Court Notice', 'MCL 600.8031'),
  requirement(2, 'COMPLAINT', 'Complaint', 'MCR 2.111'),
];

function renderUpload() {
  render(<DocumentUpload filingId={7} courtId={3} caseTypeId={11} filingType="initial"
    documents={[]} onDocumentsChange={vi.fn()} onBusyChange={vi.fn()} />);
}

const typePicker = () => screen.getByLabelText(/Document type/) as HTMLSelectElement;

function courtGroupOptions(): string[][] | null {
  const group = typePicker().querySelector(`optgroup[label="${COURT_GROUP}"]`);
  return group && [...group.querySelectorAll('option')].map(option => [option.value, option.textContent ?? '']);
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("lists the court's own document types in their own group and lets the filer pick one", async () => {
  vi.mocked(getFilingRequirements).mockResolvedValue(COURT_RULE_TYPES);
  renderUpload();

  // Only the type the catalog lacks is added; COMPLAINT keeps its catalog entry.
  await waitFor(() => expect(courtGroupOptions()).toEqual([['BUS_CT_NOTICE', 'Business Court Notice (MCL 600.8031)']]));
  expect(getFilingRequirements).toHaveBeenCalledWith(3, 11, 'initial', expect.any(AbortSignal));

  fireEvent.change(typePicker(), { target: { value: 'BUS_CT_NOTICE' } });

  expect(typePicker().value).toBe('BUS_CT_NOTICE');
  expect((screen.getByLabelText(/Document title/) as HTMLInputElement).value).toBe('Business Court Notice');
  expect(screen.getByText(/Court rule:/).textContent).toBe('Court rule: MCL 600.8031');
});

const uploaded = (id: number, type: string) => ({ id, title: `Document ${id}`, type, size: 2048, isSearchable: true });

it('labels uploaded documents from the one catalog, and from the court for a type only the court lists', async () => {
  vi.mocked(getFilingRequirements).mockResolvedValue(COURT_RULE_TYPES);
  render(<DocumentUpload filingId={7} courtId={3} caseTypeId={11} filingType="initial"
    documents={[uploaded(1, 'MOT_DEFAULT'), uploaded(2, 'FEE_WAIVER_ORDER'), uploaded(3, 'BUS_CT_NOTICE'), uploaded(4, 'LOCAL_FORM_12')]}
    onDocumentsChange={vi.fn()} onBusyChange={vi.fn()} />);

  const labels = () => screen.getAllByRole('row').slice(1).map(row => within(row).getAllByRole('cell')[1].textContent);
  await waitFor(() => expect(labels()).toEqual([
    'Motion for Default Judgment', 'Signed Fee Waiver Decision', 'Business Court Notice', 'Local Form 12',
  ]));
});

it('labels the form and its button in sentence case', async () => {
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
  renderUpload();

  expect(await screen.findByRole('heading', { name: 'Upload documents' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Upload document' })).toBeTruthy();
});

it('offers companion documents by their catalog names, in real plurals', async () => {
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
  render(<DocumentUpload filingId={7} courtId={3} caseTypeId={11} filingType="subsequent"
    documents={[uploaded(1, 'MOT_SD')]} onDocumentsChange={vi.fn()} onBusyChange={vi.fn()} />);

  expect(await screen.findByRole('button', { name: 'Add Supporting Affidavits' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Add Brief in Support of Motion' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Add Proof of Service - Electronic' })).toBeTruthy();
  expect(document.body.textContent).not.toContain('(s)');
});

it("narrows the type picker to the court's types when that category is chosen", async () => {
  vi.mocked(getFilingRequirements).mockResolvedValue(COURT_RULE_TYPES);
  renderUpload();
  const category = screen.getByLabelText('Category') as HTMLSelectElement;
  await waitFor(() => expect(within(category).getByRole('option', { name: COURT_GROUP })).toBeTruthy());

  fireEvent.change(category, { target: { value: COURT_GROUP } });

  expect([...typePicker().options].map(option => option.value)).toEqual(['', 'BUS_CT_NOTICE']);
});

it("follows the document type with its title until the filer writes their own", async () => {
  vi.mocked(getFilingRequirements).mockResolvedValue([]);
  renderUpload();
  await waitFor(() => expect(getFilingRequirements).toHaveBeenCalled());
  const title = () => screen.getByLabelText(/Document title/) as HTMLInputElement;

  fireEvent.change(typePicker(), { target: { value: 'COMPLAINT' } });
  expect(title().value).toBe('Complaint');
  fireEvent.change(typePicker(), { target: { value: 'SUMMONS' } });
  expect(title().value).toBe('Summons');

  fireEvent.change(title(), { target: { value: 'Summons to Acme Corp.' } });
  fireEvent.change(typePicker(), { target: { value: 'COMPLAINT' } });
  expect(typePicker().value).toBe('COMPLAINT');
  expect(title().value).toBe('Summons to Acme Corp.');
});

it("offers a retry when the court's document types fail to load, and retrying fetches them", async () => {
  vi.mocked(getFilingRequirements)
    .mockRejectedValueOnce(new Error('Network Error'))
    .mockResolvedValueOnce(COURT_RULE_TYPES);
  renderUpload();

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain("Could not load the document types in this court's rules.");
  expect(courtGroupOptions()).toBeNull();

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  await waitFor(() => expect(courtGroupOptions()).toEqual([['BUS_CT_NOTICE', 'Business Court Notice (MCL 600.8031)']]));
  expect(screen.queryByRole('alert')).toBeNull();
  expect(getFilingRequirements).toHaveBeenCalledTimes(2);
});
