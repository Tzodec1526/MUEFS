import { expect, it } from 'vitest';
import { DOCUMENT_LABELS, FILING_CATEGORIES, getDocumentLabel } from './documentTypes';

it.each([
  ['MOT_TRO', 'Motion for Temporary Restraining Order'],
  ['MOT_DEFAULT', 'Motion for Default Judgment'],
  ['MOT_COMPEL', 'Motion to Compel Discovery'],
  ['MOT_OTHER', 'Other Motion'],
  ['BRIEF_SUPPORT', 'Brief in Support of Motion'],
  ['BRIEF', 'Brief in Support of Motion'],
  ['ANSWER', 'Answer'],
  ['REPLY', 'Answer/Reply'],
  ['MOT_FEES', 'Motion for Attorney Fees and Costs'],
  ['POS_ELECTRONIC', 'Proof of Service - Electronic'],
  ['DISC_CERT_GF', 'Certification of Good Faith Discovery Effort'],
  ['FEE_WAIVER_ORDER', 'Signed Fee Waiver Decision'],
  ['PUBLIC_COPY', 'Reviewed Public Copy'],
])('labels %s as %s', (code, label) => {
  expect(getDocumentLabel(code)).toBe(label);
});

it('spells out a code the catalog does not know', () => {
  expect(getDocumentLabel('LOCAL_FORM_12')).toBe('Local Form 12');
});

it('gives each code in the picker one place in the catalog', () => {
  const codes = FILING_CATEGORIES.flatMap(category => category.types.map(type => type.code));
  expect(codes.length).toBe(new Set(codes).size);
});

it('uses the label the picker offers wherever that document is listed', () => {
  const motions = FILING_CATEGORIES.find(category => category.label === 'Motions');
  expect(motions?.types.find(type => type.code === 'MOT_SD')?.label).toBe('Motion for Summary Disposition');
  expect(DOCUMENT_LABELS.MOT_SD).toBe('Motion for Summary Disposition');
});
