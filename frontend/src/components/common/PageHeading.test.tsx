import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, expect, it } from 'vitest';
import PageHeading from './PageHeading';

afterEach(cleanup);

function Query() {
  return <p>Query: {useLocation().search || 'none'}</p>;
}

it('leaves focus alone on the first page load, then focuses the heading of the page it navigates to', async () => {
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

  const heading = await screen.findByRole('heading', { level: 1, name: 'Filings' });
  await waitFor(() => expect(document.activeElement).toBe(heading));
});

it('keeps focus where the user put it when only the query string changes', async () => {
  render(
    <MemoryRouter initialEntries={['/cases/search']}>
      <Routes>
        <Route path="/cases/search" element={<>
          <PageHeading>Case search</PageHeading>
          <Link to="/cases/search?party=Smith">Search for Smith</Link>
          <Query />
        </>} />
      </Routes>
    </MemoryRouter>,
  );
  const link = screen.getByRole('link', { name: 'Search for Smith' });
  link.focus();

  fireEvent.click(link);

  await screen.findByText('Query: ?party=Smith');
  expect(document.activeElement).toBe(link);
});
