import { CanceledError } from 'axios';
import { afterEach, beforeEach, expect, it, vi, type Mock } from 'vitest';
import { clearSession } from '../auth/keycloak';
import { applyDemoRole } from '../auth/session';
import { apiClient } from './client';
import { listCourtDirectory, type CourtDirectoryEntry } from './courts';

vi.mock('./client', () => ({ apiClient: { get: vi.fn() } }));

type Get = (url: string, config: { signal: AbortSignal }) => Promise<{ data: CourtDirectoryEntry[] }>;
const get = apiClient.get as unknown as Mock<Get>;

const wayne = { id: 3, name: 'Third Circuit Court', county: 'Wayne' };
const washtenaw = { id: 9, name: 'Twenty-Second Circuit Court', county: 'Washtenaw' };

function pending() {
  let resolve = (_entries: CourtDirectoryEntry[]) => {};
  let reject = (_reason: unknown) => {};
  get.mockImplementationOnce(() => new Promise((succeed, fail) => {
    resolve = entries => succeed({ data: entries });
    reject = fail;
  }));
  return { resolve: (entries: CourtDirectoryEntry[]) => resolve(entries), reject: (reason: unknown) => reject(reason) };
}

const requestSignal = (call: number) => get.mock.calls[call][1].signal;

beforeEach(() => {
  applyDemoRole('attorney');
  get.mockResolvedValue({ data: [wayne] });
});

afterEach(() => {
  clearSession();
  localStorage.clear();
  vi.resetAllMocks();
});

it('asks the server for the court directory once in a session', async () => {
  expect(await listCourtDirectory()).toEqual([wayne]);
  expect(await listCourtDirectory()).toEqual([wayne]);
  expect(await listCourtDirectory(new AbortController().signal)).toEqual([wayne]);

  expect(get).toHaveBeenCalledTimes(1);
  expect(get.mock.calls[0][0]).toBe('/courts/directory');
});

it('shares one request between callers that arrive while it is running', async () => {
  const request = pending();

  const callers = [listCourtDirectory(new AbortController().signal), listCourtDirectory(), listCourtDirectory()];
  request.resolve([wayne, washtenaw]);

  expect(await Promise.all(callers)).toEqual([[wayne, washtenaw], [wayne, washtenaw], [wayne, washtenaw]]);
  expect(get).toHaveBeenCalledTimes(1);
});

it('does not keep a failure: every waiting caller sees it and the next call asks again', async () => {
  const request = pending();
  const callers = [listCourtDirectory(), listCourtDirectory()];
  request.reject(new Error('Network Error'));

  await expect(callers[0]).rejects.toThrow('Network Error');
  await expect(callers[1]).rejects.toThrow('Network Error');

  expect(await listCourtDirectory()).toEqual([wayne]);
  expect(get).toHaveBeenCalledTimes(2);
});

it('does not keep a request the client cancelled', async () => {
  get.mockRejectedValueOnce(new CanceledError('The signed-in account changed.'));
  await expect(listCourtDirectory()).rejects.toBeInstanceOf(CanceledError);

  expect(await listCourtDirectory()).toEqual([wayne]);
  expect(get).toHaveBeenCalledTimes(2);
});

it('cancels the request when its last caller leaves, and then asks again', async () => {
  const first = new AbortController();
  const second = new AbortController();
  pending();
  const callers = [listCourtDirectory(first.signal), listCourtDirectory(second.signal)];

  first.abort();
  await expect(callers[0]).rejects.toBeInstanceOf(CanceledError);
  expect(requestSignal(0).aborted).toBe(false);

  second.abort();
  await expect(callers[1]).rejects.toBeInstanceOf(CanceledError);
  expect(requestSignal(0).aborted).toBe(true);

  expect(await listCourtDirectory()).toEqual([wayne]);
  expect(get).toHaveBeenCalledTimes(2);
});

it('keeps the running request for the callers that stay when another leaves', async () => {
  const leaving = new AbortController();
  const request = pending();
  const gone = listCourtDirectory(leaving.signal);
  const staying = listCourtDirectory();

  leaving.abort();
  await expect(gone).rejects.toBeInstanceOf(CanceledError);
  request.resolve([washtenaw]);

  expect(await staying).toEqual([washtenaw]);
  expect(requestSignal(0).aborted).toBe(false);
});

it('refuses a caller that has already left without sending a request for it', async () => {
  const left = new AbortController();
  left.abort();

  await expect(listCourtDirectory(left.signal)).rejects.toBeInstanceOf(CanceledError);

  expect(get).not.toHaveBeenCalled();
});

it('keeps the stored directory when a page that used it goes away', async () => {
  await listCourtDirectory();
  const leaving = new AbortController();

  const gone = listCourtDirectory(leaving.signal);
  leaving.abort();
  await gone.catch(() => {});

  expect(await listCourtDirectory()).toEqual([wayne]);
  expect(get).toHaveBeenCalledTimes(1);
});

it('asks again after a role switch', async () => {
  await listCourtDirectory();
  get.mockResolvedValue({ data: [washtenaw] });

  applyDemoRole('clerk');

  expect(await listCourtDirectory()).toEqual([washtenaw]);
  expect(get).toHaveBeenCalledTimes(2);
});

it('asks again after sign-out', async () => {
  await listCourtDirectory();
  get.mockResolvedValue({ data: [washtenaw] });

  clearSession();

  expect(await listCourtDirectory()).toEqual([washtenaw]);
  expect(get).toHaveBeenCalledTimes(2);
});

it('does not hand a request from the previous session to the next one', async () => {
  const earlier = pending();
  const previous = listCourtDirectory();
  applyDemoRole('clerk');
  get.mockResolvedValue({ data: [washtenaw] });

  const next = listCourtDirectory();
  earlier.resolve([wayne]);

  expect(await next).toEqual([washtenaw]);
  expect(requestSignal(0).aborted).toBe(true);
  await previous.catch(() => {});
  expect(await listCourtDirectory()).toEqual([washtenaw]);
  expect(get).toHaveBeenCalledTimes(2);
});

it('keeps a late failure of the previous session from clearing the next session\'s directory', async () => {
  const earlier = pending();
  const previous = listCourtDirectory();
  applyDemoRole('clerk');
  get.mockResolvedValue({ data: [washtenaw] });
  await listCourtDirectory();

  earlier.reject(new CanceledError('The signed-in account changed.'));
  await previous.catch(() => {});

  expect(await listCourtDirectory()).toEqual([washtenaw]);
  expect(get).toHaveBeenCalledTimes(2);
});
