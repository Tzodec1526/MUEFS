// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
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

  // getByRole fails on duplicates, so each name must identify exactly one button.
  for (const name of [
    'Sign in as Attorney', 'Sign in as Court Clerk', 'Sign in as Self-Represented Litigant',
    'Sign in as System Administrator', 'Browse records',
  ]) expect(screen.getByRole('button', { name })).toBeTruthy();
  expect(screen.queryAllByRole('button', { name: 'Sign In' })).toEqual([]);
  // The visible text stays as it was and is part of each name.
  expect(screen.getByRole('button', { name: 'Sign in as Court Clerk' }).textContent).toBe('Sign In');
});
