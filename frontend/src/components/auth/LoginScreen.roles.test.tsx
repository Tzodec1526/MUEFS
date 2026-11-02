import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import LoginScreen from './LoginScreen';

beforeEach(() => {
  vi.stubEnv('VITE_ALLOW_DEMO_MODE', 'true');
  vi.stubEnv('VITE_KEYCLOAK_URL', '');
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  localStorage.clear();
});

it('gives each demo role button a name that says which role it opens', () => {
  render(<MemoryRouter initialEntries={['/login']}><LoginScreen /></MemoryRouter>);

  for (const name of [
    'Sign in as Attorney', 'Sign in as Court clerk', 'Sign in as Self-represented litigant',
    'Sign in as System administrator', 'Browse records',
  ]) expect(screen.getByRole('button', { name })).toBeTruthy();
  expect(screen.queryAllByRole('button', { name: 'Sign in' })).toEqual([]);
  expect(screen.getByRole('button', { name: 'Sign in as Court clerk' }).textContent).toBe('Sign in');
});

it('lists each demo role with one line of description and no decoration', () => {
  render(<MemoryRouter initialEntries={['/login']}><LoginScreen /></MemoryRouter>);

  const items = within(screen.getByRole('list')).getAllByRole('listitem');
  expect(items.map(item => item.querySelector('strong')?.textContent)).toEqual([
    'Attorney', 'Court clerk', 'Self-represented litigant', 'Public docket', 'System administrator',
  ]);
  expect(items.every(item => item.querySelector('span')?.textContent)).toBe(true);
  expect(screen.queryByText(/State of Michigan/i)).toBeNull();
  expect(screen.queryByText(/Statewide Electronic Filing Portal/i)).toBeNull();
  expect(document.querySelector('svg:not(.michigan-outline)')).toBeNull();
});

it('signs in with the chosen role', () => {
  render(<MemoryRouter initialEntries={['/login']}><LoginScreen /></MemoryRouter>);

  fireEvent.click(screen.getByRole('button', { name: 'Sign in as Court clerk' }));

  expect(localStorage.getItem('demo_role')).toBe('clerk');
});

it('links to the About page', () => {
  render(<MemoryRouter initialEntries={['/login']}><LoginScreen /></MemoryRouter>);

  expect(screen.getByRole('link', { name: 'About MUEFS' }).getAttribute('href')).toBe('/about');
});
