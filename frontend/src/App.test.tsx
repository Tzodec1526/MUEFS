import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from './api/client';
import { isPublicPath } from './auth/publicPath';
import { ToastProvider } from './components/common/Toast';
import App from './App';

vi.mock('./api/client', async (importOriginal) => {
  const offline = () => Promise.reject(new Error('Unexpected API request in a component test'));
  return {
    ...await importOriginal<typeof import('./api/client')>(),
    apiClient: { get: vi.fn(), post: vi.fn(offline), put: vi.fn(offline), patch: vi.fn(offline), delete: vi.fn(offline) },
  };
});

type Answer = unknown | ((call: number) => unknown);
const get = apiClient.get as unknown as Mock<(url: string) => Promise<{ data: unknown }>>;

const forbidden = () => {
  throw { response: { status: 403, data: { detail: 'System administrator access is required.' } } };
};
const failsOnce = (data: unknown) => (call: number) => {
  if (call === 1) throw new Error('Network Error');
  return data;
};

const directory = {
  users: [{
    id: 8, first_name: 'Grace', last_name: 'Hopper', email: 'grace.hopper@example.gov', user_type: 'clerk',
    is_active: true, administration_version: 1, court_roles: [],
  }],
  total: 1, page_size: 25,
};

const stats = {
  courts_efiling_enabled: 255, public_cases_indexed: 40, total_filings: 12, pending_clerk_review: 3,
  mcr_document_types: 20, max_upload_mb: 50, mifile_max_upload_mb: 25,
};

const filerOverview = {
  filings: [
    {
      id: 11, court_id: 3, case_id: null, filer_id: 1, status: 'returned', case_title: 'Doe v. Roe', filing_description: null,
      submitted_at: '2026-03-02T12:00:00Z', rejection_reason: 'Missing signature', created_at: '2026-03-01T12:00:00Z',
      updated_at: '2026-03-03T12:00:00Z', submission_count: 1, document_count: 2,
    },
    {
      id: 12, court_id: 3, case_id: null, filer_id: 1, status: 'accepted', case_title: 'Smith v. Jones', filing_description: null,
      submitted_at: '2026-02-02T12:00:00Z', rejection_reason: null, created_at: '2026-02-01T12:00:00Z',
      updated_at: '2026-02-03T12:00:00Z', submission_count: 1, document_count: 1,
    },
    {
      id: 13, court_id: 3, case_id: null, filer_id: 1, status: 'draft', case_title: null, filing_description: null,
      submitted_at: null, rejection_reason: null, created_at: '2026-01-02T12:00:00Z',
      updated_at: '2026-01-02T12:00:00Z', submission_count: 0, document_count: 0,
    },
  ],
  total: 8,
  status_counts: { draft: 2, returned: 1, accepted: 5 },
  court_names: { 3: 'Third Circuit Court' },
};

const queueOverview = {
  filings: [], total: 4, page_size: 1, submitted_count: 3, under_review_count: 1, waiting_48h: 2,
  oldest_submitted_at: null, as_of: '2026-03-03T12:00:00Z',
};

function serve(userType: string, answers: Record<string, Answer>) {
  const responses: Record<string, Answer> = {
    '/auth/me': { id: 3, user_type: userType, court_assignments: [] },
    '/notifications': { notifications: [], total: 0, page_size: 25, email_enabled: false },
    ...answers,
  };
  get.mockImplementation(async (url) => {
    if (!(url in responses)) throw new Error(`Unexpected request: ${url}`);
    const answer = responses[url];
    return { data: typeof answer === 'function' ? answer(get.mock.calls.filter(([called]) => called === url).length) : answer };
  });
}

function openApp(entry: string, role: string) {
  localStorage.setItem('demo_role', role);
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[entry]}>
        <App />
      </MemoryRouter>
    </ToastProvider>,
  );
}

const requested = (url: string) => get.mock.calls.some(([called]) => called === url);

async function settle() {
  await waitFor(() => expect(requested('/auth/me')).toBe(true));
  await waitFor(() => expect(screen.queryByText(/^(Loading page|Checking administrator access|Loading court assignments)/))
    .toBeNull());
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

it('shows a system administrator the account directory at /admin', async () => {
  serve('admin', {
    '/admin/access': { system_admin: true, user_id: 3, courts: [{ id: 3, name: 'Third Circuit Court' }] },
    '/admin/users': directory,
  });
  openApp('/admin', 'admin');

  expect(await screen.findByRole('heading', { name: 'People and court access' })).toBeTruthy();
  expect(await screen.findByRole('button', { name: 'Manage Grace Hopper' })).toBeTruthy();
  expect(screen.getByText('grace.hopper@example.gov')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Provision account' })).toBeTruthy();
});

it.each(['attorney', 'srl', 'clerk', 'public'])('tells a %s that /admin needs administrator access, without asking the server', async (role) => {
  const userType = { attorney: 'attorney', srl: 'self_represented', clerk: 'clerk', public: 'public' }[role]!;
  serve(userType, {
    '/admin/access': forbidden,
    '/admin/users': directory,
  });
  openApp('/admin', role);

  await settle();

  expect(await screen.findByRole('heading', { name: 'Administrator access required' })).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
  expect(screen.queryByRole('heading', { name: 'People and court access' })).toBeNull();
  expect(screen.queryByText(/Grace Hopper|grace\.hopper@example\.gov/)).toBeNull();
  expect(screen.queryByRole('button', { name: 'Provision account' })).toBeNull();
  expect(requested('/admin/access')).toBe(false);
  expect(requested('/admin/users')).toBe(false);
});

it('shows a delegated court administrator the account directory at /admin', async () => {
  serve('clerk', {
    '/auth/me': { id: 2, user_type: 'clerk', court_assignments: [{ court_id: 3, role: 'admin', court_name: 'Third Circuit Court' }] },
    '/admin/access': { system_admin: false, user_id: 2, courts: [{ id: 3, name: 'Third Circuit Court' }] },
    '/admin/users': directory,
  });
  openApp('/admin', 'clerk');

  expect(await screen.findByRole('heading', { name: 'People and court access' })).toBeTruthy();
  expect(await screen.findByRole('button', { name: 'Manage Grace Hopper' })).toBeTruthy();
});

it('shows a failed profile load at /admin as that failure, and lets a court administrator in after a retry', async () => {
  serve('clerk', {
    '/auth/me': failsOnce({ id: 2, user_type: 'clerk', court_assignments: [{ court_id: 3, role: 'admin', court_name: 'Third Circuit Court' }] }),
    '/admin/access': { system_admin: false, user_id: 2, courts: [{ id: 3, name: 'Third Circuit Court' }] },
    '/admin/users': directory,
  });
  openApp('/admin', 'clerk');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Could not verify court assignments.');
  expect(screen.getAllByRole('heading', { level: 1 }).map(h1 => h1.textContent)).toEqual(['Administrator access not checked']);

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  expect(await screen.findByRole('button', { name: 'Manage Grace Hopper' })).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
});

it('shows an administrator a failed account directory load inline and loads it again on retry', async () => {
  serve('admin', {
    '/admin/access': { system_admin: true, user_id: 3, courts: [] },
    '/admin/users': failsOnce(directory),
  });
  openApp('/admin', 'admin');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Could not load accounts.');

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  expect(await screen.findByRole('button', { name: 'Manage Grace Hopper' })).toBeTruthy();
  expect(screen.queryByText('Could not load accounts.')).toBeNull();
});

it('shows an administrator a refused account directory once, inline, with no retry', async () => {
  serve('admin', {
    '/admin/access': { system_admin: true, user_id: 3, courts: [] },
    '/admin/users': forbidden,
  });
  openApp('/admin', 'admin');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('System administrator access is required.');
  expect(screen.getAllByText('System administrator access is required.')).toHaveLength(1);
  expect(within(alert).queryByRole('button', { name: 'Retry' })).toBeNull();
});

it("shows a failed load of a filer's filings inline and loads them again on retry", async () => {
  serve('attorney', {
    '/filings': failsOnce({ filings: [], total: 0, status_counts: {}, court_names: {} }),
  });
  openApp('/filings', 'attorney');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain("We couldn't load your filings. Please retry.");

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  await waitFor(() => expect(get.mock.calls.filter(([url]) => url === '/filings')).toHaveLength(2));
  await waitFor(() => expect(screen.queryByText("We couldn't load your filings. Please retry.")).toBeNull());
});

it('tells a filer when their filing counts fail to load, and loads them again on retry', async () => {
  serve('attorney', {
    '/filings': failsOnce(filerOverview),
  });
  openApp('/', 'attorney');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Could not load your filings.');

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  expect(await screen.findByText(/drafts in progress/)).toBeTruthy();
  expect(screen.getByText(/returned for correction/)).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
});

it('tells a clerk when the pending review count fails to load, and loads it again on retry', async () => {
  serve('clerk', {
    '/auth/me': { id: 2, user_type: 'clerk', court_assignments: [{ court_id: 3, role: 'clerk', court_name: 'Third Circuit Court' }] },
    '/clerk/queue': failsOnce(queueOverview),
  });
  openApp('/', 'clerk');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Could not load the number of filings pending review.');

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  expect(await screen.findByText(/4 filings pending review/)).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
});

it('shows that platform statistics did not load instead of hiding them, and loads them again on retry', async () => {
  serve('public', { '/public/stats': failsOnce(stats) });
  openApp('/about', 'public');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Platform statistics are unavailable right now.');

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  expect(await screen.findByText('Public cases indexed')).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
});

function holdCall(url: string, call: number) {
  const served = get.getMockImplementation()!;
  let reject!: (reason: unknown) => void;
  const held = new Promise<never>((_, fail) => { reject = fail; });
  get.mockImplementation(async (requested) =>
    requested === url && get.mock.calls.filter(([called]) => called === url).length === call ? held : served(requested));
  return reject;
}

it.each([
  ['the filing counts', 'attorney', '/', '/filings', /drafts in progress/],
  ['the platform statistics', 'public', '/about', '/public/stats', /Public cases indexed/],
])('keeps %s from the latest retry when an earlier retry fails later', async (_name, role, entry, url, loaded) => {
  serve(role, { [url]: failsOnce(url === '/public/stats' ? stats : filerOverview) });
  const failEarlierRetry = holdCall(url, 2);
  openApp(entry, role);
  const retry = within(await screen.findByRole('alert')).getByRole('button', { name: 'Retry' });

  fireEvent.click(retry);
  fireEvent.click(retry);
  expect(await screen.findByText(loaded)).toBeTruthy();
  await act(async () => failEarlierRetry(new Error('Network Error')));

  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByText(loaded)).toBeTruthy();
});

it('states the number of e-filing courts the platform reports', async () => {
  serve('public', { '/public/stats': stats });
  openApp('/about', 'public');

  const card = (await screen.findByText('Courts accepting e-filing')).closest<HTMLElement>('.platform-stat-card')!;
  expect(within(card).getByText('255')).toBeTruthy();
  expect(screen.queryByText(/All Michigan courts/i)).toBeNull();
});

it.each([
  ['/login', 'attorney', {}, 'Attorney'],
  ['/about', 'attorney', {}, 'Courts accepting e-filing'],
  ['/', 'attorney', { '/filings': filerOverview }, 'Your filings'],
  ['/', 'clerk', {
    '/auth/me': { id: 2, user_type: 'clerk', court_assignments: [{ court_id: 3, role: 'clerk', court_name: 'Third Circuit Court' }] },
    '/clerk/queue': queueOverview,
  }, 'Open review queue'],
])('claims no statewide court coverage at %s for a %s', async (entry, role, answers, loaded) => {
  serve(role, { '/public/stats': stats, ...answers });
  localStorage.setItem('demo_role', role);
  render(<ToastProvider><MemoryRouter initialEntries={[entry]}><App /></MemoryRouter></ToastProvider>);

  await screen.findByText(loaded);
  expect(document.body.textContent).not.toMatch(/(all|any) Michigan courts?/i);
});

const clerkAtThirdCircuit = {
  '/auth/me': { id: 2, user_type: 'clerk', court_assignments: [{ court_id: 3, role: 'clerk', court_name: 'Third Circuit Court' }] },
};

it.each([
  ['/login', 'attorney', 'Sign in'],
  ['/', 'attorney', 'Your filings'],
  ['/', 'public', 'Public court records'],
  ['/', 'clerk', 'Clerk dashboard · Third Circuit Court'],
  ['/about', 'attorney', 'About'],
  ['/filing/new', 'attorney', 'New filing'],
  ['/filings', 'attorney', 'My filings'],
  ['/filings/7/history', 'attorney', 'Filing #7: receipts and history'],
  ['/filings/7/fees', 'attorney', 'Filing #7: fees and payments'],
  ['/filings/7/filing-date', 'clerk', 'Filing #7: record a filing-date order · Third Circuit Court'],
  ['/cases/search', 'public', 'Case search'],
  ['/cases/42', 'public', 'Case docket'],
  ['/courts/3/calendar', 'clerk', 'Filing calendar'],
  ['/courts/3/intake', 'clerk', 'Filing intake'],
  ['/notifications', 'attorney', 'Notices and email status'],
  ['/service/deliveries', 'attorney', 'Document delivery inbox'],
  ['/service/deliveries/5', 'attorney', 'Document delivery record'],
  ['/filings/7/deliveries', 'attorney', 'Filing #7: document deliveries'],
  ['/filings/7/deliveries/new', 'attorney', 'Send documents · Filing #7'],
  ['/admin', 'admin', 'People and court access'],
  ['/admin', 'attorney', 'Administrator access required'],
  ['/cases/42/participants', 'clerk', 'Case access and participants'],
  ['/cases/42/participants/9/service-contact', 'clerk', 'Service instructions'],
  ['/clerk/cases', 'clerk', 'Court cases · Third Circuit Court'],
  ['/documents/5/publication', 'clerk', 'Document public access'],
  ['/favorites', 'attorney', 'Favorites'],
  ['/clerk/queue', 'clerk', 'Review queue · Third Circuit Court'],
  ['/clerk/fee-reviews', 'clerk', 'Fee reviews · Third Circuit Court'],
  ['/clerk/payment-register', 'clerk', 'Receipt register · Third Circuit Court'],
  ['/no-such-page', 'attorney', 'Page not found'],
])('titles %s for a %s "%s · MUEFS"', async (entry, role, title) => {
  serve({ srl: 'self_represented' }[role] ?? role, role === 'clerk' ? clerkAtThirdCircuit : {});
  document.title = '';
  openApp(entry, role);

  await waitFor(() => expect(document.title).toBe(`${title} · MUEFS`));
});

it.each([
  ['/login', 'attorney', 'Sign in'],
  ['/', 'attorney', 'Your filings'],
  ['/', 'public', 'Public court records'],
  ['/', 'clerk', 'Third Circuit Court'],
  ['/about', 'public', 'About MUEFS'],
  ['/filing/new', 'attorney', 'New filing'],
  ['/filings', 'attorney', 'My filings'],
  ['/filings/7/history', 'attorney', 'Filing #7: receipts and history'],
  ['/filings/7/fees', 'attorney', 'Filing #7: fees and payments'],
  ['/filings/7/filing-date', 'clerk', 'Filing #7: record a filing-date order'],
  ['/cases/search', 'public', 'Case search'],
  ['/notifications', 'attorney', 'Notices and email status'],
  ['/service/deliveries', 'attorney', 'Document delivery inbox'],
  ['/service/deliveries/5', 'attorney', 'Document delivery record'],
  ['/filings/7/deliveries', 'attorney', 'Filing #7: document deliveries'],
  ['/filings/7/deliveries/new', 'attorney', 'Send documents'],
  ['/admin', 'attorney', 'Administrator access required'],
  ['/cases/42/participants', 'clerk', 'Case access and participants'],
  ['/cases/42/participants/9/service-contact', 'clerk', 'Service instructions'],
  ['/clerk/cases', 'clerk', 'Court cases'],
  ['/documents/5/publication', 'clerk', 'Document public access'],
  ['/favorites', 'attorney', 'Favorites'],
  ['/clerk/queue', 'clerk', 'Review queue'],
  ['/clerk/fee-reviews', 'clerk', 'Fee reviews'],
  ['/clerk/payment-register', 'clerk', 'Receipt register'],
  ['/no-such-page', 'attorney', 'Page not found'],
])('heads %s for a %s with one h1, "%s"', async (entry, role, heading) => {
  serve({ srl: 'self_represented' }[role] ?? role, role === 'clerk' ? clerkAtThirdCircuit : {});
  openApp(entry, role);

  await waitFor(() => expect(screen.getAllByRole('heading', { level: 1 }).map(h1 => h1.textContent)).toEqual([heading]));
  expect(screen.queryByRole('heading', { name: 'Michigan Unified E-Filing System' })).toBeNull();
});

const refused = (status: number) => () => {
  throw { response: { status, data: {} } };
};

it.each([
  ['/auth/callback', 'attorney', {}, 'Sign-in not completed', 'Sign-in failed. Return to the login page and try again.'],
  ['/cases/42', 'public', { '/cases/42': refused(404) }, 'Case not found', 'Case not found.'],
  ['/cases/42', 'public', { '/cases/42': refused(403) }, 'Case not available',
    'This case is sealed or confidential and is not available for public viewing.'],
  ['/cases/42', 'public', { '/cases/42': failsOnce({}) }, 'Case not loaded', 'Failed to load case details.'],
  ['/filing/new?filing_id=7', 'attorney', { '/filings/7': failsOnce({}) }, 'Filing #7 not loaded',
    'Could not load this filing. Please retry.'],
  ['/filing/new', 'attorney', { '/auth/me': failsOnce({}) }, 'Filing workspace not loaded', 'Could not verify court assignments.'],
  ['/courts/3/intake', 'clerk', { ...clerkAtThirdCircuit, '/courts/3/intake': failsOnce({}) }, 'Filing intake not loaded',
    'Could not load court intake information.'],
])('heads a failed %s for a %s with one h1 and an alert', async (entry, role, answers, heading, message) => {
  serve(role, { '/cases/42/filings': [], ...answers });
  openApp(entry, role);

  await waitFor(() => expect(screen.getAllByRole('heading', { level: 1 }).map(h1 => h1.textContent)).toEqual([heading]));
  expect(screen.getByRole('alert').textContent).toContain(message);
  await waitFor(() => expect(document.title).toBe(`${heading} · MUEFS`));
});

it('heads the administration page and a case docket with their own names once their data loads', async () => {
  serve('admin', {
    '/admin/access': { system_admin: true, user_id: 3, courts: [] },
    '/admin/users': directory,
  });
  const admin = openApp('/admin', 'admin');
  await waitFor(() => expect(screen.getAllByRole('heading', { level: 1 }).map(h1 => h1.textContent))
    .toEqual(['People and court access']));
  admin.unmount();
  localStorage.clear();

  serve('public', {
    '/cases/42': {
      id: 42, court_id: 3, case_number: '2026-000042-CZ', case_type_id: 11, title: 'Smith v. Jones',
      can_manage_records: false, can_file: false, status: 'open', filed_date: '2026-03-02',
      filing_date: '2026-03-02', judge_id: null, participants: [], created_at: '2026-03-02T12:00:00Z',
    },
    '/cases/42/filings': [],
    '/courts/3': { id: 3, name: 'Third Circuit Court' },
    '/courts/3/case-types': [],
  });
  openApp('/cases/42', 'public');
  await waitFor(() => expect(screen.getAllByRole('heading', { level: 1 }).map(h1 => h1.textContent))
    .toEqual(['Smith v. Jones']));
});

it('moves focus to the new page heading after a navigation, but not on the first page load', async () => {
  serve('attorney', {
    '/filings': { filings: [], total: 0, status_counts: {}, court_names: {} },
  });
  openApp('/', 'attorney');
  await screen.findByRole('heading', { level: 1, name: 'Your filings' });
  expect(document.activeElement).toBe(document.body);

  fireEvent.click(within(screen.getByRole('complementary')).getByRole('link', { name: 'My filings' }));

  const heading = await screen.findByRole('heading', { level: 1, name: 'My filings' });
  await waitFor(() => expect(document.activeElement).toBe(heading));
});

it('puts the sign-in page inside a main landmark', async () => {
  serve('attorney', {});
  openApp('/login', 'attorney');

  const main = await screen.findByRole('main');
  expect(within(main).getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy();
  expect(within(main).getByRole('button', { name: 'Sign in as Attorney' })).toBeTruthy();
});

const mainNavigation = () => screen.findByRole('navigation', { name: 'Main' });
const linkNames = (navigation: HTMLElement) => within(navigation).getAllByRole('link').map(link => link.textContent);

it.each([
  ['attorney', 'New filing'],
  ['srl', 'New filing'],
  ['clerk', 'Review queue'],
  ['admin', 'People and court access'],
  ['public', 'Case search'],
])('leads the one navigation with the main task of a %s', async (role, mainTask) => {
  serve({ srl: 'self_represented' }[role] ?? role, role === 'clerk' ? clerkAtThirdCircuit : {});
  openApp('/no-such-page', role);

  const navigation = await mainNavigation();
  await waitFor(() => expect(linkNames(navigation)[0]).toBe(mainTask));
  expect(screen.getAllByRole('navigation')).toHaveLength(1);
});

it('gives an administrator no Dashboard item, since the dashboard is the People and court access page', async () => {
  serve('admin', {});
  openApp('/no-such-page', 'admin');

  expect(linkNames(await mainNavigation())).not.toContain('Dashboard');
});

it('keeps the navigation to plain text links with no filler block', async () => {
  serve('clerk', clerkAtThirdCircuit);
  openApp('/no-such-page', 'clerk');

  const navigation = await mainNavigation();
  await waitFor(() => expect(linkNames(navigation)).toContain('Filing intake'));
  expect(new Set(linkNames(navigation)).size).toBe(linkNames(navigation).length);
  expect(navigation.querySelector('svg')).toBeNull();
  expect(screen.queryByText('Quick Info')).toBeNull();
});

it('marks the current page in the navigation', async () => {
  serve('attorney', { '/filings': { filings: [], total: 0, status_counts: {}, court_names: {} } });
  openApp('/filings', 'attorney');

  const navigation = await mainNavigation();
  expect(within(navigation).getByRole('link', { name: 'My filings' }).getAttribute('aria-current')).toBe('page');
  expect(within(navigation).getByRole('link', { name: 'Case search' }).getAttribute('aria-current')).toBeNull();
});

it('opens the small-screen menu and closes it when a link is chosen', async () => {
  serve('attorney', { '/filings': { filings: [], total: 0, status_counts: {}, court_names: {} } });
  openApp('/no-such-page', 'attorney');
  const navigation = await mainNavigation();
  const toggle = screen.getByRole('button', { name: 'Menu' });
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  expect(document.getElementById(toggle.getAttribute('aria-controls')!)).toBe(within(navigation).getByRole('list'));

  fireEvent.click(toggle);

  expect(screen.getByRole('button', { name: 'Close menu' }).getAttribute('aria-expanded')).toBe('true');
  expect(screen.getByRole('complementary').className).toContain('open');

  fireEvent.click(within(navigation).getByRole('link', { name: 'My filings' }));

  expect(screen.getByRole('button', { name: 'Menu' }).getAttribute('aria-expanded')).toBe('false');
  expect(screen.getByRole('complementary').className).not.toContain('open');
});

it('shows the demo notice as plain text, not a live region', async () => {
  serve('attorney', {});
  openApp('/no-such-page', 'attorney');

  const notice = await screen.findByText(/not for real filings/);
  expect(notice.tagName).toBe('P');
  expect(notice.closest('[aria-live], [role="status"], [role="alert"]')).toBeNull();
});

function openAnonymously(entry: string) {
  return render(<ToastProvider><MemoryRouter initialEntries={[entry]}><App /></MemoryRouter></ToastProvider>);
}

it('opens the About page without a session, with the comparison and the live statistics', async () => {
  serve('public', { '/public/stats': stats });
  openAnonymously('/about');

  expect(await screen.findByRole('heading', { level: 1, name: 'About MUEFS' })).toBeTruthy();
  expect(screen.getByRole('heading', { level: 2, name: 'MUEFS compared with MiFILE' })).toBeTruthy();
  expect(screen.getByRole('table')).toBeTruthy();
  expect(await screen.findByText('Public cases indexed')).toBeTruthy();
  await waitFor(() => expect(document.title).toBe('About · MUEFS'));
  expect(requested('/auth/me')).toBe(false);
});

it('sends an anonymous visitor to sign-in for a private page, unlike About', async () => {
  serve('public', {});
  openAnonymously('/filings');

  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy();
});

it.each(['/about', '/about/', '/cases/search', '/cases/42', '/courts/3/intake'])('treats %s as a public path', (pathname) => {
  expect(isPublicPath(pathname)).toBe(true);
});

it.each(['/', '/filings', '/about/team', '/aboutus', '/cases/42/participants'])('treats %s as a private path', (pathname) => {
  expect(isPublicPath(pathname)).toBe(false);
});

it('states what delivery and draft editing really do', async () => {
  serve('public', { '/public/stats': stats });
  openAnonymously('/about');

  const row = (name: string) => screen.getByRole('rowheader', { name }).closest('tr')!;
  expect((await screen.findByRole('rowheader', { name: 'Service-only records' })).closest('tr')!.textContent)
    .toContain('opt-in delivery to reviewed recipients');
  expect(row('Draft editing').textContent).toContain('Save to your account');
  expect(row('Draft editing').textContent).toContain('compare conflicting versions');
  expect(document.body.textContent).not.toMatch(/arrange delivery outside the app|Browser draft recovery|autosave/i);
});

it('links to About from the app shell', async () => {
  serve('attorney', { '/public/stats': stats });
  openApp('/no-such-page', 'attorney');

  fireEvent.click(within(await screen.findByRole('contentinfo')).getByRole('link', { name: 'About MUEFS' }));

  expect(await screen.findByRole('heading', { level: 1, name: 'About MUEFS' })).toBeTruthy();
});

it.each([
  ['/login', 'attorney', {}, 'Attorney'],
  ['/', 'attorney', { '/filings': filerOverview }, 'Your filings'],
  ['/', 'public', {}, 'Public court records'],
  ['/', 'clerk', { ...clerkAtThirdCircuit, '/clerk/queue': queueOverview }, 'Open review queue'],
])('keeps the comparison and the platform statistics off %s for a %s', async (entry, role, answers, loaded) => {
  serve(role, { '/public/stats': stats, ...answers });
  openApp(entry, role);

  await screen.findByText(loaded);
  expect(screen.queryByText(/MiFILE/)).toBeNull();
  expect(screen.queryByText('Courts accepting e-filing')).toBeNull();
  expect(requested('/public/stats')).toBe(false);
});

const filingsRequests = () => (get.mock.calls as unknown as [string, { params?: Record<string, unknown> }?][])
  .filter(([url]) => url === '/filings')
  .map(([, config]) => config?.params);

const lastFilingsRequest = () => filingsRequests().slice(-1)[0];

it('leads a filer with returned filings, drafts, recent filings and starting a filing', async () => {
  serve('attorney', { '/filings': filerOverview });
  openApp('/', 'attorney');

  const main = await screen.findByRole('main');
  expect(within(main).getByRole('link', { name: 'Start a filing' }).getAttribute('href')).toBe('/filing/new');
  const returned = await within(main).findByRole('link', { name: /returned for correction/ });
  const drafts = within(main).getByRole('link', { name: /drafts in progress/ });
  expect(returned.textContent).toBe('1 returned for correction');
  expect(drafts.getAttribute('href')).toBe('/filings?status=draft');
  expect(returned.compareDocumentPosition(drafts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  const recent = within(within(main).getByRole('region', { name: 'Recent filings' }));
  expect(recent.getByRole('link', { name: 'Doe v. Roe' }).getAttribute('href')).toBe('/filing/new?filing_id=11');
  expect(recent.getByRole('link', { name: 'Smith v. Jones' }).getAttribute('href')).toBe('/filings/12/history');
  expect(recent.getByRole('link', { name: 'Untitled filing' }).getAttribute('href')).toBe('/filing/new?filing_id=13');
  expect(recent.getByText('Accepted')).toBeTruthy();
  expect(recent.getAllByText(/Third Circuit Court/)).toHaveLength(3);
  expect(filingsRequests()[0]).toEqual({ page_size: 5 });
  expect(within(main).queryByRole('link', { name: 'Search cases' })).toBeNull();
});

it('tells a filer with no filings how to start', async () => {
  serve('attorney', { '/filings': { filings: [], total: 0, status_counts: {}, court_names: {} } });
  openApp('/', 'attorney');

  expect(await screen.findByText(/You have no filings yet/)).toBeTruthy();
  expect(screen.queryByRole('link', { name: /returned for correction/ })).toBeNull();
  expect(screen.queryByRole('link', { name: /in progress/ })).toBeNull();
});

it('opens the filings filtered to returned ones from the dashboard', async () => {
  serve('attorney', { '/filings': filerOverview });
  openApp('/', 'attorney');

  fireEvent.click(await screen.findByRole('link', { name: /returned for correction/ }));

  const filter = await screen.findByLabelText('Filter by status') as HTMLSelectElement;
  expect(filter.value).toBe('returned');
  await waitFor(() => expect(lastFilingsRequest()).toMatchObject({ status: 'returned', page: 1 }));
});

it('ignores a status it does not know in the filings address', async () => {
  serve('attorney', { '/filings': filerOverview });
  openApp('/filings?status=constructor', 'attorney');

  const filter = await screen.findByLabelText('Filter by status') as HTMLSelectElement;
  expect(filter.value).toBe('');
  await waitFor(() => expect(lastFilingsRequest()).toMatchObject({ status: undefined }));
});

it('lets the filter on the filings page change the status it asks for', async () => {
  serve('attorney', { '/filings': filerOverview });
  openApp('/filings?status=returned', 'attorney');

  fireEvent.change(await screen.findByLabelText('Filter by status'), { target: { value: 'draft' } });

  await waitFor(() => expect(lastFilingsRequest()).toMatchObject({ status: 'draft' }));
  fireEvent.change(screen.getByLabelText('Filter by status'), { target: { value: '' } });
  await waitFor(() => expect(lastFilingsRequest()).toMatchObject({ status: undefined }));
});

it('leads a clerk with the queue counts and the way into the queue', async () => {
  serve('clerk', { ...clerkAtThirdCircuit, '/clerk/queue': queueOverview });
  openApp('/', 'clerk');

  const link = await screen.findByRole('link', { name: 'Open review queue' });
  expect(link.getAttribute('href')).toBe('/clerk/queue');
  expect(await screen.findByText('4 filings pending review')).toBeTruthy();
  const count = (name: string) => screen.getByText(name).closest('div')!.querySelector('dd')!.textContent;
  expect(count('Submitted')).toBe('3');
  expect(count('Under review')).toBe('1');
  expect(count('Waiting 48+ hours')).toBe('2');
});

it('leads the public home with a case search that opens the matching results', async () => {
  serve('public', {});
  openApp('/', 'public');

  fireEvent.change(await screen.findByLabelText('Party name'), { target: { value: ' Smith ' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search cases' }));

  expect(await screen.findByRole('heading', { level: 1, name: 'Case search' })).toBeTruthy();
  expect((screen.getByLabelText('Party name') as HTMLInputElement).value).toBe('Smith');
});

const recoveryCopy = 'muefs_filing_draft:v2:1:new';

it('keeps a draft-recovery copy and the session when the filer declines Switch role', async () => {
  sessionStorage.setItem(recoveryCopy, '{}');
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  serve('attorney', {});
  openApp('/no-such-page', 'attorney');

  fireEvent.click(await screen.findByRole('button', { name: 'Switch role' }));

  expect(confirm).toHaveBeenCalledOnce();
  expect(confirm.mock.calls[0][0]).toContain('discards the unsaved filing edits');
  expect(sessionStorage.getItem(recoveryCopy)).toBe('{}');
  expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeTruthy();
});

it.each([
  ['a recovery copy in this tab', () => sessionStorage.setItem(recoveryCopy, '{}')],
  ['an older recovery copy', () => localStorage.setItem('muefs_filing_draft', '{}')],
])('discards %s once the filer confirms Switch role', async (_name, store) => {
  store();
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  serve('attorney', {});
  openApp('/no-such-page', 'attorney');

  fireEvent.click(await screen.findByRole('button', { name: 'Switch role' }));

  expect(confirm).toHaveBeenCalledOnce();
  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy();
  expect(sessionStorage.getItem(recoveryCopy)).toBeNull();
  expect(localStorage.getItem('muefs_filing_draft')).toBeNull();
});

it('switches role without asking when no recovery copy exists', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  serve('attorney', {});
  openApp('/no-such-page', 'attorney');

  fireEvent.click(await screen.findByRole('button', { name: 'Switch role' }));

  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy();
  expect(confirm).not.toHaveBeenCalled();
});
