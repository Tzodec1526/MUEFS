import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from './api/client';
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

  expect(await screen.findByRole('heading', { name: 'People & court access' })).toBeTruthy();
  expect(await screen.findByRole('heading', { name: 'Grace Hopper' })).toBeTruthy();
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
  expect(screen.queryByRole('heading', { name: 'People & court access' })).toBeNull();
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

  expect(await screen.findByRole('heading', { name: 'People & court access' })).toBeTruthy();
  expect(await screen.findByRole('heading', { name: 'Grace Hopper' })).toBeTruthy();
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

  expect(await screen.findByRole('heading', { name: 'Grace Hopper' })).toBeTruthy();
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
    '/filings/summary': failsOnce({ draft: 2, returned: 1 }),
    '/public/stats': stats,
  });
  openApp('/', 'attorney');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Could not load your filing counts.');

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  expect(await screen.findByText(/drafts in progress/)).toBeTruthy();
  expect(screen.getByText(/returned for correction/)).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
});

it('tells a clerk when the pending review count fails to load, and loads it again on retry', async () => {
  serve('clerk', {
    '/auth/me': { id: 2, user_type: 'clerk', court_assignments: [{ court_id: 3, role: 'clerk', court_name: 'Third Circuit Court' }] },
    '/clerk/queue': failsOnce({ filings: [], total: 4, page: 1, page_size: 1 }),
    '/public/stats': stats,
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
  openApp('/', 'public');

  const alert = await screen.findByRole('alert');
  expect(alert.textContent).toContain('Platform statistics are unavailable right now.');

  fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

  expect(await screen.findByText('Public cases indexed')).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
});

it('states the number of e-filing courts the platform reports', async () => {
  serve('public', { '/public/stats': stats });
  openApp('/', 'public');

  const card = (await screen.findByText('Courts accepting e-filing')).closest<HTMLElement>('.platform-stat-card')!;
  expect(within(card).getByText('255')).toBeTruthy();
  expect(screen.queryByText(/All Michigan courts/i)).toBeNull();
});

it.each([
  ['/login', 'attorney', {}],
  ['/', 'attorney', { '/filings/summary': { draft: 0, returned: 0 } }],
  ['/', 'clerk', {
    '/auth/me': { id: 2, user_type: 'clerk', court_assignments: [{ court_id: 3, role: 'clerk', court_name: 'Third Circuit Court' }] },
    '/clerk/queue': { filings: [], total: 0, page: 1, page_size: 1 },
  }],
])('claims no statewide court coverage at %s for a %s', async (entry, role, answers) => {
  serve(role, { '/public/stats': stats, ...answers });
  localStorage.setItem('demo_role', role);
  render(<ToastProvider><MemoryRouter initialEntries={[entry]}><App /></MemoryRouter></ToastProvider>);

  await screen.findByText(entry === '/login' ? 'Attorney' : 'Courts accepting e-filing');
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
  ['/filing/new', 'attorney', 'New filing'],
  ['/filings', 'attorney', 'My filings'],
  ['/filings/7/history', 'attorney', 'Filing #7 history'],
  ['/filings/7/fees', 'attorney', 'Filing #7 fees and payments'],
  ['/filings/7/filing-date', 'clerk', 'Filing #7 filing date · Third Circuit Court'],
  ['/cases/search', 'public', 'Case search'],
  ['/cases/42', 'public', 'Case docket'],
  ['/courts/3/calendar', 'clerk', 'Filing calendar'],
  ['/courts/3/intake', 'clerk', 'Filing intake'],
  ['/notifications', 'attorney', 'Notices and email status'],
  ['/service/deliveries', 'attorney', 'Document delivery inbox'],
  ['/service/deliveries/5', 'attorney', 'Document delivery record'],
  ['/filings/7/deliveries', 'attorney', 'Filing #7 deliveries'],
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
