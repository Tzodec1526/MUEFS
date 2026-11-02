import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import AuthCallback from './AuthCallback';

vi.mock('../../auth/keycloak', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../auth/keycloak')>(),
  handleKeycloakCallback: () => new Promise(() => {}),
}));

afterEach(cleanup);

it('heads the sign-in callback with one h1 while the court sign-in completes', () => {
  render(<MemoryRouter initialEntries={['/auth/callback']}><AuthCallback /></MemoryRouter>);

  expect(screen.getAllByRole('heading', { level: 1 }).map(h1 => h1.textContent)).toEqual(['Completing sign-in']);
  expect(screen.getByRole('status').textContent).toBe('Completing sign-in…');
});
