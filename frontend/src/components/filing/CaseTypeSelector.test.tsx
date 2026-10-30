import { useState } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { getCaseTypes, getFilingRequirements, type CaseType, type FilingRequirement } from '../../api/courts';
import CaseTypeSelector from './CaseTypeSelector';

vi.mock('../../api/courts', () => ({ getCaseTypes: vi.fn(), getFilingRequirements: vi.fn() }));

const civil: CaseType = {
  id: 11, court_id: 3, code: 'CIV-GEN', name: 'General Civil', category: 'civil', filing_fee_cents: 17500,
  description: 'Contract and other civil claims', is_active: true,
};
const divorce: CaseType = {
  id: 12, court_id: 3, code: 'FAM-DIV', name: 'Divorce', category: 'domestic_relations', filing_fee_cents: 0,
  description: null, is_active: true,
};
const complaint: FilingRequirement = {
  id: 1, document_type_code: 'COMPLAINT', is_required: true, description: 'Complaint', mcr_reference: 'MCR 2.111',
  local_rule_reference: null, page_limit: 25, format_notes: null,
};
const exhibit: FilingRequirement = {
  id: 2, document_type_code: 'EXHIBIT', is_required: false, description: 'Exhibits', mcr_reference: 'MCR 9.999',
  local_rule_reference: null, page_limit: null, format_notes: 'Label each exhibit.',
};

function Harness() {
  const [selected, setSelected] = useState<number | null>(null);
  return <CaseTypeSelector courtId={3} selectedCaseTypeId={selected} onSelect={setSelected} />;
}

beforeEach(() => {
  vi.mocked(getCaseTypes).mockResolvedValue([civil, divorce]);
  vi.mocked(getFilingRequirements).mockResolvedValue([complaint, exhibit]);
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('lists the case types as one radio group with their fees and no internal codes', async () => {
  render(<Harness />);

  const group = await screen.findByRole('group', { name: 'Case type' });
  await within(group).findByRole('radio', { name: /General Civil/ });
  expect(within(group).getAllByRole('radio').map(radio => radio.closest('label')?.textContent)).toEqual([
    'General Civil$175.00Contract and other civil claims', 'DivorceNo fee',
  ]);
  expect(document.body.textContent).not.toMatch(/CIV-GEN|FAM-DIV/);
  expect(screen.queryByRole('button', { name: /General Civil/ })).toBeNull();
});

it('marks the chosen case type and loads its requirements', async () => {
  render(<Harness />);

  fireEvent.click(await screen.findByRole('radio', { name: /Divorce/ }));

  expect((screen.getByRole('radio', { name: /Divorce/ }) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole('radio', { name: /General Civil/ }) as HTMLInputElement).checked).toBe(false);
  await screen.findByRole('heading', { name: 'Required documents (1)' });
  expect(getFilingRequirements).toHaveBeenCalledWith(3, 12, 'initial', expect.anything());
});

it('writes requirements as a plain checklist with the rule cited as text and no document codes', async () => {
  render(<Harness />);

  fireEvent.click(await screen.findByRole('radio', { name: /General Civil/ }));

  const required = await screen.findByRole('heading', { name: 'Required documents (1)' });
  const list = required.nextElementSibling as HTMLElement;
  expect(within(list).getAllByRole('listitem').map(item => item.textContent)).toEqual(['Complaint (MCR 2.111)Page limit: 25 pages']);
  expect(within(list).getByRole('link', { name: 'MCR 2.111' }).getAttribute('href')).toMatch(/rule-2111-general-rules-of-pleading$/);
  expect(screen.getByRole('heading', { name: 'Optional documents (1)' }).nextElementSibling?.textContent)
    .toBe('Exhibits (MCR 9.999)Label each exhibit.');
  expect(screen.queryByRole('link', { name: 'MCR 9.999' })).toBeNull();
  expect(document.body.textContent).not.toMatch(/COMPLAINT|EXHIBIT/);
});

it('links statutes to the section page and court rules to the rule page', async () => {
  const citing = (id: number, mcr_reference: string): FilingRequirement => ({ ...complaint, id, mcr_reference });
  vi.mocked(getFilingRequirements).mockResolvedValue([
    citing(1, 'MCL 600.2201 et seq.'), citing(2, 'MCL 600.2912d'), citing(3, 'MCL 600.2950(3)'), citing(4, 'MCR 2.111'),
  ]);
  render(<Harness />);

  fireEvent.click(await screen.findByRole('radio', { name: /General Civil/ }));

  const hrefFor = async (name: string) => (await screen.findByRole('link', { name })).getAttribute('href');
  const statute = 'https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-';
  expect(await hrefFor('MCL 600.2201 et seq.')).toBe(`${statute}600-2201`);
  expect(await hrefFor('MCL 600.2912d')).toBe(`${statute}600-2912d`);
  expect(await hrefFor('MCL 600.2950(3)')).toBe(`${statute}600-2950`);
  expect(await hrefFor('MCR 2.111')).toMatch(/rule-2111-general-rules-of-pleading$/);
});

it('finds case types by name, not by internal code', async () => {
  render(<Harness />);
  await screen.findByRole('radio', { name: /General Civil/ });

  fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'civ-gen' } });
  expect(screen.getByText('No case types match your filters.')).toBeTruthy();

  fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'divor' } });
  expect(screen.getAllByRole('radio')).toHaveLength(1);
});

it('spells out a category made of two words', async () => {
  const smallClaims = { ...civil, id: 13, name: 'Small Claims Court', category: 'small_claims' };
  vi.mocked(getCaseTypes).mockResolvedValue([civil, smallClaims]);
  render(<Harness />);

  await screen.findByText('Small Claims Court');

  expect(within(screen.getByLabelText('Category')).getAllByRole('option').map(option => option.textContent))
    .toEqual(['All categories', 'Civil', 'Small Claims']);
  expect(document.body.textContent).not.toMatch(/small_claims/i);
});

it('narrows the list by category', async () => {
  render(<Harness />);
  await screen.findByRole('radio', { name: /General Civil/ });

  fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'domestic_relations' } });

  expect(screen.getAllByRole('radio').map(radio => radio.closest('label')?.textContent)).toEqual(['DivorceNo fee']);
});

const radioLabels = () => screen.getAllByRole('radio').map(radio => radio.closest('label')?.textContent);

it('keeps the chosen case type on screen when a category filter would hide it', async () => {
  render(<Harness />);
  fireEvent.click(await screen.findByRole('radio', { name: /Divorce/ }));

  fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'civil' } });

  expect(radioLabels()).toEqual(['General Civil$175.00Contract and other civil claims', 'DivorceNo fee']);
  expect((screen.getByRole('radio', { name: /Divorce/ }) as HTMLInputElement).checked).toBe(true);
  expect(screen.queryByText('No case types match your filters.')).toBeNull();
});

it('says no other case type matched when a search leaves only the chosen case type', async () => {
  render(<Harness />);
  fireEvent.click(await screen.findByRole('radio', { name: /General Civil/ }));
  await screen.findByRole('heading', { name: 'Required documents (1)' });

  fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'probate' } });

  expect(radioLabels()).toEqual(['General Civil$175.00Contract and other civil claims']);
  expect((screen.getByRole('radio', { name: /General Civil/ }) as HTMLInputElement).checked).toBe(true);
  expect(screen.queryByText('No other case types match your filters.')).not.toBeNull();
  expect(screen.queryByText('No case types match your filters.')).toBeNull();
  expect(screen.getByRole('heading', { name: 'Required documents (1)' })).toBeTruthy();
});

it('drops an unchosen case type from the list as soon as the choice moves away from it', async () => {
  render(<Harness />);
  fireEvent.click(await screen.findByRole('radio', { name: /Divorce/ }));
  fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'civil' } });

  fireEvent.click(screen.getByRole('radio', { name: /General Civil/ }));

  expect(radioLabels()).toEqual(['General Civil$175.00Contract and other civil claims']);
});
