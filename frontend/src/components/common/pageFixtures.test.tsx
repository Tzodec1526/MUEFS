import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from '../../api/client';
import { CourtContext } from '../auth/CourtSession';
import FeeReviewQueue from '../clerk/FeeReviewQueue';
import FilingDateOrderPage from '../clerk/FilingDateOrderPage';
import PaymentRegisterPage from '../clerk/PaymentRegisterPage';
import CaseParticipantsPage from '../courts/CaseParticipantsPage';
import CourtCalendarPage from '../courts/CourtCalendarPage';
import CourtIntakePage from '../courts/CourtIntakePage';
import DocumentPublicationPage from '../courts/DocumentPublicationPage';
import ServiceContactPage from '../courts/ServiceContactPage';
import FilingFeesPage from '../filing/FilingFeesPage';
import FilingHistoryPage from '../filing/FilingHistoryPage';
import NotificationsPage from '../notifications/NotificationsPage';
import Favorites from '../search/Favorites';
import DeliveriesPage from '../service/DeliveriesPage';
import DeliveryComposePage from '../service/DeliveryComposePage';
import DeliveryDetailPage from '../service/DeliveryDetailPage';
import { ToastProvider } from './Toast';

vi.mock('../../api/client', async (importOriginal) => {
  const offline = () => Promise.reject(new Error('Unexpected API request in a component test'));
  return {
    ...await importOriginal<typeof import('../../api/client')>(),
    apiClient: { get: vi.fn(offline), post: vi.fn(offline), put: vi.fn(offline), patch: vi.fn(offline), delete: vi.fn(offline) },
  };
});

const get = apiClient.get as unknown as Mock<(url: string) => Promise<{ data: unknown }>>;
const time = '2026-03-02T12:00:00Z';
const court = { court_id: 3, court_name: '3rd Circuit Court', role: 'admin' };
const document = {
  id: 2, title: 'Complaint', document_type_code: 'COMPLAINT', file_size_bytes: 2048, sha256_hash: 'abc', is_confidential: false,
  page_count: 2, pii_warnings: [], created_at: time,
};
const copy = { id: 9, document_id: 2, title: 'Complaint', file_size_bytes: 2048, sha256_hash: 'def', page_count: 1, pii_warnings: [], created_at: time };
const intake = {
  court_id: 3, court_name: '3rd Circuit Court', version: 2, is_efiling_enabled: false, public_notice: 'Closed today.',
  case_types: [{ id: 1, code: 'CZ', name: 'General Civil', is_active: true }],
};
const fees = {
  filing_id: 2, version: 1, payment_version: 1, source: 'court', assessment_id: 'a-1', authority_reference: 'Schedule 1',
  items: [{ fee_type: 'filing', amount_cents: 17500, description: 'Filing fee' }], total_cents: 17500, paid_cents: 0,
  balance_due_cents: 17500, overpaid_cents: 0, review_requested_at: null, review_reason: null, assessment_stale: false,
  can_request_review: false, can_assess: true, can_pay: true, can_request_waiver: true, obligation_met: false,
  payments_simulated: true, can_manage_external_payments: true, can_record_external_payment: true,
  filing: {
    id: 2, details_token: 't', documents: [], fee_waiver_requested: false, fee_waiver_granted: null,
    case_title: 'Doe v. Roe', filing_type: 'service_only', status: 'under_review',
  },
};
const delivery = {
  id: 'd-1', packet_id: 'p-1', source_transaction_id: 't-1', filing_id: 2, sender: 'Pat Lee', created_at: time,
  court_name: '3rd Circuit Court', case_number: '2026-000001-CZ', case_title: 'Doe v. Roe', documents: [document],
  contact: { name: 'Sam Roe', email: 'sam@example.com', authority: 'Registration' }, delivery_status: 'sent', last_error: null, message_id: 'm-1',
  can_acknowledge: false, can_retry: false, can_report_failure: false,
};
const responses: Record<string, unknown> = {
  '/courts/3': { id: 3, name: '3rd Circuit Court' },
  '/courts/3/calendars': {
    calendars: [{
      id: 1, timezone: 'America/Detroit', valid_from: '2026-01-01', valid_through: '2026-12-31',
      closed_dates: { '2026-09-07': 'Labor Day' }, authority_reference: 'Order 1', published_at: time,
    }],
    total: 1, can_publish: true,
  },
  '/courts/3/intake': { ...intake, can_manage: true },
  '/courts/3/intake/history': {
    changes: [{ id: 1, timestamp: time, actor_name: 'Dana Whitfield', reason: 'Closed', authority_reference: 'Order 1', before: intake, after: intake }],
    total: 1,
  },
  '/cases/1/participants': {
    case_number: '2026-000001-CZ', title: 'Doe v. Roe', is_sealed: false, participant_version: 1, actor_id: 1, total: 1,
    participants: [{
      id: 1, party_name: 'Jane Doe', role: 'plaintiff', account_email: null, user_id: null, attorney_bar_number: null,
      represented_party_name: null, is_active: true, access_enabled: false, reviewed_at: time,
    }],
  },
  '/cases/1/participants/history': { total: 0, events: [] },
  '/cases/1/participants/1/service-contact': {
    court_id: 3, case_number: '2026-000001-CZ', title: 'Doe v. Roe', participant_version: 1,
    participant: { party_name: 'Jane Doe', role: 'plaintiff', represented_party_name: null },
    verified_email: null, can_edit: true, contact: null, issues: [],
  },
  '/cases/1/participants/1/service-contact/history': { total: 0, events: [] },
  '/clerk/documents/2/publication': {
    document, filing_id: 2, case_id: 1, filing_status: 'accepted', version: 1, current_copy: copy, copies: [copy], total: 1,
    publication_block: null, can_withhold: true,
  },
  '/clerk/documents/2/publication/history': { total: 0, events: [] },
  '/clerk/filings/2/filing-date': {
    filing_id: 2, court_id: 3, status: 'accepted', submission_count: 1, submitted_at: time, filing_date: '2026-03-02',
    filing_date_basis: null, version: 1, case_id: 1, case_number: '2026-000001-CZ', case_filing_date: '2026-03-02',
    case_date_version: 1, order_block: null,
  },
  '/clerk/fee-reviews': {
    total: 1, page: 1, filings: [{ id: 2, case_title: 'Doe v. Roe', filer_name: 'Pat Lee', status: 'submitted', requested_at: time }],
  },
  '/clerk/payment-register': {
    court_id: 3, date_from: '2026-03-01', date_to: '2026-03-31', timezone: 'America/Detroit', range_start: time, range_end: time,
    generated_at: time, include_simulated: false, total: 1, page: 1, entries: [],
    totals: { credits_cents: 0, reversals_cents: 0, net_cents: 0 }, simulated_totals: { credits_cents: 0, reversals_cents: 0, net_cents: 0 },
  },
  '/filings/2/fees': fees,
  '/filings/2/payments': { payments: [], total: 0, page: 1, payment_version: 1 },
  '/filings/2/history': {
    filing_id: 2, status: 'accepted', submission_count: 1, total: 2, page: 1, page_size: 25, court_id: 3, can_manage_documents: true,
    filing_date: '2026-03-02', filing_date_basis: null,
    fee_waiver: {
      granted: null, referred_at: null, decided_at: null, amount_due_cents: null, balance_due_cents: null, fee_version: 1,
      can_pay: false, payments_simulated: true, allowed_actions: ['refer'],
    },
    transactions: [{
      id: 't-1', submission_number: 1, event_type: 'submitted', actor_name: 'Pat Lee', occurred_at: time,
      details: {
        document_id: 2, public_copy: copy,
        fee_assessment: { source: 'court', assessment_id: 'a-1', total_cents: 100, paid_cents: 0, balance_due_cents: 100 },
      },
    }, {
      id: 't-2', submission_number: 1, event_type: 'submitted', actor_name: 'Pat Lee', occurred_at: time,
      details: { documents: [document] },
    }],
  },
  '/notifications': {
    total: 1, email_enabled: true,
    notifications: [{
      id: 7, filing_envelope_id: 12, delivery_id: null, type: 'filing_accepted', subject: 'Filing #12 accepted', body: 'Accepted.',
      delivery_status: 'failed', created_at: time, email_recipient: null, attempt_count: 1, last_error: null, sent_at: null, next_attempt_at: null,
    }],
  },
  '/notifications/7/delivery': { events: [], total: 0, page: 1, message_id: null, can_retry: false },
  '/service/deliveries': {
    total: 1, page_size: 25,
    deliveries: [{ id: 'd-1', name: null, actor_name: 'Pat Lee', email: null, created_at: time, delivery_status: 'sent' }],
  },
  '/service/deliveries/d-1': delivery,
  '/service/deliveries/d-1/events': { events: [], total: 0 },
  '/service/filings/2/options': {
    enabled: true, source_transaction_id: 't-1', case_number: '2026-000001-CZ', case_title: 'Doe v. Roe', court_name: '3rd Circuit Court',
    documents: [document], total: 1, page_size: 25,
    recipients: [{
      participant_id: 1, name: 'Sam Roe', role: 'defendant', represented_party_name: null, contact_id: 5, version: 1,
      method: 'electronic', email: 'sam@example.com', address: null, authority: 'Registration', issues: [],
    }],
  },
  '/favorites': {
    total: 1,
    favorites: [{ id: 1, case_id: 1, case_title: 'Doe v. Roe', case_number: '2026-000001-CZ', court_name: '3rd Circuit Court', created_at: time }],
  },
  '/favorites/courts': {
    total: 1, favorites: [{ id: 1, court_id: 3, court_name: '3rd Circuit Court', county: 'Wayne', court_type: 'circuit', created_at: time }],
  },
};

function skips() {
  const levels = screen.getAllByRole('heading').map(heading => Number(heading.tagName[1]));
  return levels.flatMap((level, index) => (index && level > levels[index - 1] + 1 ? [`h${levels[index - 1]} to h${level}`] : []));
}

function show(url: string, path: string, page: ReactNode) {
  render(<MemoryRouter initialEntries={[url]}>
    <ToastProvider>
      <CourtContext.Provider value={{ userId: 1, role: 'clerk', courts: [court], court, loading: false, selectCourt: vi.fn(), refresh: vi.fn() } as never}>
        <Routes><Route path={path} element={page} /></Routes>
      </CourtContext.Provider>
    </ToastProvider>
  </MemoryRouter>);
}

beforeEach(() => {
  get.mockImplementation((url: string) => (url in responses
    ? Promise.resolve({ data: responses[url] })
    : Promise.reject(new Error(`No fixture for ${url}`))));
});

afterEach(() => {
  cleanup();
  get.mockReset();
});

it.each([
  ['intake', '/courts/3/intake', '/courts/:courtId/intake', <CourtIntakePage key="p" />, 'Notice from the court'],
  ['calendar', '/courts/3/calendar', '/courts/:courtId/calendar', <CourtCalendarPage key="p" />, 'Calendar revision #1'],
  ['filing history', '/filings/2/history', '/filings/:filingId/history', <FilingHistoryPage key="p" />, 'Documents recorded (1)'],
  ['fees', '/filings/2/fees', '/filings/:filingId/fees', <FilingFeesPage key="p" />, 'Payment or waiver'],
  ['favorites', '/favorites', '/favorites', <Favorites key="p" />, 'Doe v. Roe'],
  ['participants', '/cases/1/participants', '/cases/:caseId/participants', <CaseParticipantsPage key="p" />, '2026-000001-CZ · Doe v. Roe'],
  ['service contact', '/cases/1/participants/1/service-contact', '/cases/:caseId/participants/:participantId/service-contact', <ServiceContactPage key="p" />, 'Record service instructions'],
  ['document publication', '/documents/2/publication', '/documents/:documentId/publication', <DocumentPublicationPage key="p" />, 'Filed original'],
  ['filing date order', '/filings/2/filing-date', '/filings/:filingId/filing-date', <FilingDateOrderPage key="p" />, 'Current record'],
  ['fee review queue', '/clerk/fee-reviews', '/clerk/fee-reviews', <FeeReviewQueue key="p" />, 'Filing #2: Doe v. Roe'],
  ['receipt register', '/clerk/payment-register', '/clerk/payment-register', <PaymentRegisterPage key="p" />, /through 2026-03-31/],
  ['notices', '/notifications', '/notifications', <NotificationsPage key="p" />, 'Filing #12 accepted'],
  ['delivery inbox', '/service/deliveries', '/service/deliveries', <DeliveriesPage key="p" />, 'Documents from Pat Lee'],
  ['delivery record', '/service/deliveries/d-1', '/service/deliveries/:deliveryId', <DeliveryDetailPage key="p" />, 'Documents in this delivery'],
  ['delivery compose', '/filings/2/deliveries/new', '/filings/:filingId/deliveries/new', <DeliveryComposePage key="p" />, 'Recipients and service instructions'],
])('steps down one heading level at a time on the %s page', async (_name, url, path, page, heading) => {
  show(url, path, page);
  await screen.findByRole('heading', { name: heading });
  expect(skips()).toEqual([]);
});

it('steps down from the fees heading to the opened payment records', async () => {
  show('/filings/2/fees', '/filings/:filingId/fees', <FilingFeesPage />);
  fireEvent.click(await screen.findByRole('button', { name: 'View payment records' }));
  await screen.findByRole('heading', { name: 'Payment records for filing #2' });
  expect(skips()).toEqual([]);
});

it('steps down from a notice to its opened email history', async () => {
  show('/notifications', '/notifications', <NotificationsPage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Email history' }));
  await screen.findByRole('heading', { name: 'Email history for notice #7' });
  expect(skips()).toEqual([]);
});

it('keeps the fees heading a level under the wizard step when no level is passed', async () => {
  const { default: PaymentForm } = await import('../filing/PaymentForm');
  show('/filing', '/filing', <><h2>Review your filing</h2><PaymentForm filingId={2} /></>);
  const heading = await screen.findByRole('heading', { name: 'Filing fees and payments' });
  expect(heading.tagName).toBe('H3');
  expect(screen.getByRole('heading', { name: 'Payment or waiver' }).tagName).toBe('H4');
  expect(skips()).toEqual([]);
});

it.each([
  ['notices', '/notifications', '/notifications', <NotificationsPage key="p" />, '1 notice'],
  ['email attempts', '/notifications', '/notifications', <NotificationsPage key="p" />, /· 1 email attempt$/],
  ['submissions', '/filings/2/history', '/filings/:filingId/history', <FilingHistoryPage key="p" />, '1 recorded submission'],
  ['public copy pages', '/documents/2/publication', '/documents/:documentId/publication', <DocumentPublicationPage key="p" />, /· 1 page$/],
  ['register entries', '/clerk/payment-register', '/clerk/payment-register', <PaymentRegisterPage key="p" />, /^1 recorded entry · /],
  ['participants', '/filings/2/deliveries/new', '/filings/:filingId/deliveries/new', <DeliveryComposePage key="p" />, /^1 active case participant\. /],
])('counts %s in the singular', async (_name, url, path, page, count) => {
  show(url, path, page);
  expect(await screen.findByText(count)).toBeTruthy();
});

it('names case types without their internal codes on the intake page', async () => {
  show('/courts/3/intake', '/courts/:courtId/intake', <CourtIntakePage />);
  await screen.findByRole('cell', { name: 'General Civil' });
  expect(window.document.body.textContent).not.toContain('(CZ)');
});

it.each([
  ['a document filing status', '/documents/2/publication', '/documents/:documentId/publication', <DocumentPublicationPage key="p" />, /· Accepted$/],
  ['a fee source', '/filings/2/history', '/filings/:filingId/history', <FilingHistoryPage key="p" />, /^Fee record at submission: Court assessment · total/],
  ['a recipient role', '/filings/2/deliveries/new', '/filings/:filingId/deliveries/new', <DeliveryComposePage key="p" />, /· Defendant/],
  ['a service method', '/filings/2/deliveries/new', '/filings/:filingId/deliveries/new', <DeliveryComposePage key="p" />, /^Electronic through portal · /],
])('shows %s in words', async (_name, url, path, page, words) => {
  show(url, path, page);
  expect(await screen.findByText(words)).toBeTruthy();
});

it('shows the filing type and status in words on the fee assessment form', async () => {
  show('/filings/2/fees', '/filings/:filingId/fees', <FilingFeesPage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Review fee assessment' }));
  expect((await screen.findByText(/Service only · Under review/)).textContent).toBe('Doe v. Roe · Service only · Under review');
});

it('counts a selected delivery in the singular', async () => {
  show('/filings/2/deliveries/new', '/filings/:filingId/deliveries/new', <DeliveryComposePage />);
  for (const box of await screen.findAllByRole('checkbox')) fireEvent.click(box);
  expect(await screen.findByText('1 document · 1 recipient')).toBeTruthy();
});
