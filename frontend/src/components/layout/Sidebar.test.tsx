import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { CourtContext } from '../auth/CourtSession';
import Sidebar from './Sidebar';

vi.mock('../../auth/session', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../auth/session')>(), hasAdministrationAccess: () => false,
}));

function openSidebar() {
  return render(
    <MemoryRouter>
      <CourtContext.Provider value={{ role: 'attorney', courts: [], court: undefined, loading: false, selectCourt: () => {}, refresh: () => {} }}>
        <button>Before the sidebar</button>
        <Sidebar />
      </CourtContext.Provider>
    </MemoryRouter>,
  );
}

const menu = () => screen.getByRole('button', { name: /menu/i });
const navigation = () => screen.getByRole('navigation', { name: 'Main' });
const links = () => within(navigation()).getAllByRole('link');

beforeEach(() => {
  openSidebar();
});

afterEach(cleanup);

it('puts the Menu button before the links it reveals, so the next Tab reaches them', () => {
  const position = menu().compareDocumentPosition(links()[0]);

  expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(links()).toHaveLength(7);
});

it('names what the button controls and whether it is open', () => {
  expect(menu().getAttribute('aria-expanded')).toBe('false');
  expect(document.getElementById(menu().getAttribute('aria-controls')!)).toBe(within(navigation()).getByRole('list'));

  fireEvent.click(menu());

  expect(menu().getAttribute('aria-expanded')).toBe('true');
  expect(menu().textContent).toBe('Close menu');
});

it('closes on Escape and gives focus back to the button', () => {
  fireEvent.click(menu());
  links()[2].focus();

  fireEvent.keyDown(document.activeElement!, { key: 'Escape' });

  expect(menu().getAttribute('aria-expanded')).toBe('false');
  expect(menu().textContent).toBe('Menu');
  expect(document.activeElement).toBe(menu());
});

it('leaves focus alone when Escape is pressed with the menu closed', () => {
  const elsewhere = screen.getByRole('button', { name: 'Before the sidebar' });
  elsewhere.focus();

  fireEvent.keyDown(elsewhere, { key: 'Escape' });

  expect(document.activeElement).toBe(elsewhere);
});

it('ignores other keys while open', () => {
  fireEvent.click(menu());

  fireEvent.keyDown(menu(), { key: 'a' });

  expect(menu().getAttribute('aria-expanded')).toBe('true');
});

it('closes when a link is chosen', () => {
  fireEvent.click(menu());

  fireEvent.click(links()[1]);

  expect(menu().getAttribute('aria-expanded')).toBe('false');
});
