import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi, type Mock } from 'vitest';
import { apiClient } from '../../api/client';
import AdministrationPage from './AdministrationPage';

vi.mock('../../api/client', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/client')>(), apiClient: { get: vi.fn() },
}));

const get = apiClient.get as unknown as Mock<(url: string) => Promise<{ data: unknown }>>;

const account = (id: number, first_name: string, last_name: string, user_type: string, is_active = true) => ({
  id, first_name, last_name, email: `${first_name.toLowerCase()}@demo.muefs.gov`, user_type, is_active,
  administration_version: 1, court_roles: [],
});

function serve(users: unknown[], total = users.length) {
  const responses: Record<string, unknown> = {
    '/admin/access': { system_admin: true, user_id: 99, courts: [{ id: 3, name: 'Third Circuit Court' }] },
    '/admin/users': { users, total, page_size: 25 },
    '/admin/users/1/history': { total: 0, events: [] },
  };
  get.mockImplementation(async (url) => {
    if (!(url in responses)) throw new Error(`Unexpected request: ${url}`);
    return { data: responses[url] };
  });
}

const open = () => render(<MemoryRouter><AdministrationPage /></MemoryRouter>);

beforeEach(() => {
  serve([account(1, 'Dana', 'Whitfield', 'clerk'), account(2, 'Maria', 'Williams', 'self_represented', false)]);
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('lists the accounts as one list, each with its identity, type, state and action', async () => {
  open();

  const directory = await screen.findByRole('region', { name: 'Account directory' });
  const rows = await within(directory).findAllByRole('listitem');
  expect(rows.map(row => row.textContent)).toEqual([
    'Dana Whitfielddana@demo.muefs.govCourt staff · ActiveManage Dana Whitfield',
    'Maria Williamsmaria@demo.muefs.govSelf-represented filer · InactiveManage Maria Williams',
  ]);
  expect(document.querySelector('article')).toBeNull();
});

it('counts accounts in real plurals', async () => {
  serve([account(1, 'Dana', 'Whitfield', 'clerk')]);
  open();

  expect(await screen.findByText('1 account')).toBeTruthy();
});

it('uses the full width for the list until an account is open', async () => {
  open();
  await screen.findByRole('button', { name: 'Manage Dana Whitfield' });
  const workspace = screen.getByRole('region', { name: 'Account directory' }).parentElement as HTMLElement;
  expect(workspace.className).toBe('admin-workspace');

  fireEvent.click(screen.getByRole('button', { name: 'Manage Dana Whitfield' }));

  expect(await screen.findByRole('heading', { level: 2, name: 'Dana Whitfield' })).toBeTruthy();
  expect(workspace.className).toBe('admin-workspace editor-open');
});

it('steps down one heading level at a time', async () => {
  open();
  fireEvent.click(await screen.findByRole('button', { name: 'Manage Dana Whitfield' }));
  await screen.findByRole('heading', { level: 3, name: 'Court access' });

  const levels = screen.getAllByRole('heading').map(heading => Number(heading.tagName[1]));
  expect(levels[0]).toBe(1);
  expect(levels.filter((level, index) => index > 0 && level > levels[index - 1] + 1)).toEqual([]);
});
