import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it } from 'vitest';
import PageHeading from './PageHeading';

afterEach(cleanup);

it('leaves focus alone on the first page load, then focuses the heading of the page it navigates to', () => {
  render(
    <MemoryRouter initialEntries={['/drafts']}>
      <Link to="/filings">Open filings</Link>
      <Routes>
        <Route path="/drafts" element={<PageHeading>Drafts</PageHeading>} />
        <Route path="/filings" element={<PageHeading>Filings</PageHeading>} />
      </Routes>
    </MemoryRouter>,
  );
  expect(document.activeElement).toBe(document.body);

  fireEvent.click(screen.getByRole('link', { name: 'Open filings' }));

  expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: 'Filings' }));
});
