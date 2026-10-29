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

const typePicker = () => screen.getByLabelText(/Document Type/) as HTMLSelectElement;

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
  expect((screen.getByLabelText(/Document Title/) as HTMLInputElement).value).toBe('Business Court Notice');
  expect(screen.getByText(/Court Rule:/).textContent).toBe('Court Rule: MCL 600.8031');
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
  const title = () => screen.getByLabelText(/Document Title/) as HTMLInputElement;

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
