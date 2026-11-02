import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Link, MemoryRouter, Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { afterEach, expect, it } from 'vitest';
import PageHeading, { HeadingFocusScope } from './PageHeading';

afterEach(cleanup);

function Query() {
  return <p>Query: {useLocation().search || 'none'}</p>;
}

it('leaves focus alone on the first page load, then focuses the heading of the page it navigates to', async () => {
  render(
    <MemoryRouter initialEntries={['/drafts']}>
      <HeadingFocusScope>
      <Link to="/filings">Open filings</Link>
      <Routes>
        <Route path="/drafts" element={<PageHeading>Drafts</PageHeading>} />
        <Route path="/filings" element={<PageHeading>Filings</PageHeading>} />
      </Routes>
      </HeadingFocusScope>
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
      <HeadingFocusScope>
      <Routes>
        <Route path="/cases/search" element={<>
          <PageHeading>Case search</PageHeading>
          <Link to="/cases/search?party=Smith">Search for Smith</Link>
          <Query />
        </>} />
      </Routes>
      </HeadingFocusScope>
    </MemoryRouter>,
  );
  const link = screen.getByRole('link', { name: 'Search for Smith' });
  link.focus();

  fireEvent.click(link);

  await screen.findByText('Query: ?party=Smith');
  expect(document.activeElement).toBe(link);
});

function Keyed() {
  const location = useLocation();
  return <Wizard key={location.key} />;
}

function Wizard() {
  const [searchParams] = useSearchParams();
  return <>
    <PageHeading>New filing</PageHeading>
    <p>Filing: {searchParams.get('filing_id') || 'unsaved'}</p>
  </>;
}

function SaveDraft() {
  const navigate = useNavigate();
  return <button onClick={() => navigate('/filing/new?filing_id=5', { replace: true })}>Save draft</button>;
}

it('keeps focus where it was when a replace changes only the query string and remounts the page', async () => {
  render(
    <MemoryRouter initialEntries={['/drafts', '/filing/new']} initialIndex={1}>
      <HeadingFocusScope>
      <SaveDraft />
      <Routes>
        <Route path="/filing/new" element={<Keyed />} />
      </Routes>
      </HeadingFocusScope>
    </MemoryRouter>,
  );
  const save = screen.getByRole('button', { name: 'Save draft' });
  save.focus();

  fireEvent.click(save);

  await screen.findByText('Filing: 5');
  expect(document.activeElement).toBe(save);
});

function Back() {
  const navigate = useNavigate();
  return <button onClick={() => navigate(-1)}>Back</button>;
}

it('focuses the heading when the user goes back to the first page of the session', async () => {
  render(
    <MemoryRouter initialEntries={['/drafts']}>
      <HeadingFocusScope>
      <Link to="/filings">Open filings</Link>
      <Back />
      <Routes>
        <Route path="/drafts" element={<section><PageHeading>Drafts</PageHeading></section>} />
        <Route path="/filings" element={<div><PageHeading>Filings</PageHeading></div>} />
      </Routes>
      </HeadingFocusScope>
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('link', { name: 'Open filings' }));
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: 'Filings' })));

  fireEvent.click(screen.getByRole('button', { name: 'Back' }));

  const heading = await screen.findByRole('heading', { level: 1, name: 'Drafts' });
  await waitFor(() => expect(document.activeElement).toBe(heading));
});

it('focuses the heading on a return to a page after passing through a page that never showed a heading', async () => {
  render(
    <MemoryRouter initialEntries={['/drafts']}>
      <HeadingFocusScope>
      <Link to="/filings">Open filings</Link>
      <Link to="/drafts">Open drafts</Link>
      <Routes>
        <Route path="/drafts" element={<PageHeading>Drafts</PageHeading>} />
        <Route path="/filings" element={<p>Loading filings…</p>} />
      </Routes>
      </HeadingFocusScope>
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('link', { name: 'Open filings' }));
  await screen.findByText('Loading filings…');

  fireEvent.click(screen.getByRole('link', { name: 'Open drafts' }));

  const heading = await screen.findByRole('heading', { level: 1, name: 'Drafts' });
  await waitFor(() => expect(document.activeElement).toBe(heading));
});

it('leaves focus alone when the first page load redirects to another page', async () => {
  render(
    <MemoryRouter initialEntries={['/']}>
      <HeadingFocusScope>
        <Routes>
          <Route path="/" element={<Navigate to="/drafts" replace />} />
          <Route path="/drafts" element={<PageHeading>Drafts</PageHeading>} />
        </Routes>
      </HeadingFocusScope>
    </MemoryRouter>,
  );

  await screen.findByRole('heading', { level: 1, name: 'Drafts' });
  expect(document.activeElement).toBe(document.body);
});

it('gives a new router no memory of the pages an earlier router visited', async () => {
  const first = render(
    <MemoryRouter initialEntries={['/drafts']}>
      <HeadingFocusScope>
        <Link to="/filings">Open filings</Link>
        <Routes>
          <Route path="/drafts" element={<PageHeading>Drafts</PageHeading>} />
          <Route path="/filings" element={<PageHeading>Filings</PageHeading>} />
        </Routes>
      </HeadingFocusScope>
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('link', { name: 'Open filings' }));
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: 'Filings' })));
  first.unmount();

  render(
    <MemoryRouter initialEntries={['/cases/search']}>
      <HeadingFocusScope>
        <Routes>
          <Route path="/cases/search" element={<PageHeading>Case search</PageHeading>} />
        </Routes>
      </HeadingFocusScope>
    </MemoryRouter>,
  );

  await screen.findByRole('heading', { level: 1, name: 'Case search' });
  expect(document.activeElement).toBe(document.body);
});

it('leaves focus alone when the page is reloaded on an entry the router had already visited', async () => {
  render(
    <MemoryRouter initialEntries={[{ pathname: '/cases/search', key: 'visited' }]}>
      <HeadingFocusScope>
      <Routes>
        <Route path="/cases/search" element={<PageHeading>Case search</PageHeading>} />
      </Routes>
      </HeadingFocusScope>
    </MemoryRouter>,
  );

  await screen.findByRole('heading', { level: 1, name: 'Case search' });
  expect(document.activeElement).toBe(document.body);
});
