import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from '../../api/client';
import type { FilingFees } from '../../api/documents';
import PaymentRecordsPanel from './PaymentRecordsPanel';

vi.mock('../../api/client', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/client')>(), apiClient: { get: vi.fn() },
}));

const get = apiClient.get as unknown as Mock<(url: string) => Promise<{ data: unknown }>>;
const fees = { filing_id: 2, payment_version: 1, can_record_external_payment: false } as unknown as FilingFees;
const payment = { id: 1, amount_cents: 1000, status: 'completed', transaction_ref: 'T-1', is_simulated: true, created_at: '2026-03-02T12:00:00Z' };

afterEach(() => {
  cleanup();
  get.mockReset();
});

it.each([
  [[payment], '1 payment record'],
  [[payment, { ...payment, id: 2 }], '2 payment records'],
])('counts the payment records in a real plural', async (payments, count) => {
  get.mockResolvedValue({ data: { payments, total: payments.length, page: 1, payment_version: 1 } });
  render(<MemoryRouter><PaymentRecordsPanel fees={fees} Heading="h3" onChanged={vi.fn()} onBusyChange={vi.fn()} /></MemoryRouter>);

  expect(await screen.findByText(count)).toBeTruthy();
});
