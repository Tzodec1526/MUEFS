import assert from 'node:assert/strict';
import test from 'node:test';
import proxy from './proxy.js';

test('paths cannot redirect the proxy away from its configured origin', async t => {
  const forwarded = [];
  const response = new Response('upstream');
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    forwarded.push({ url, options });
    return response;
  });
  const paths = ['/api/v1/cases/search?q=Smith', '//other.invalid/path', '///other.invalid/path'];
  for (const path of paths) {
    assert.equal(await proxy.fetch(new Request(`https://portal.invalid${path}`)), response);
  }
  const origin = forwarded[0].url.origin;
  assert.notEqual(origin, 'https://portal.invalid');
  for (const { url, options } of forwarded) {
    assert.equal(url.origin, origin);
    assert.equal(options.headers.get('Host'), url.host);
    assert.equal(options.redirect, 'manual');
  }
  assert.equal(forwarded[0].url.search, '?q=Smith');
  assert.equal(forwarded[1].url.pathname, '//other.invalid/path');
});

test('uploads pass through as streams', async t => {
  const request = new Request('https://portal.invalid/api/v1/filings/1/documents', {
    method: 'POST', body: 'test upload', headers: { 'Content-Type': 'text/plain' },
  });
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url.pathname, '/api/v1/filings/1/documents');
    assert.equal(options.body, request.body);
    assert.equal(options.method, 'POST');
    assert.equal(options.headers.get('Content-Type'), 'text/plain');
    return new Response('uploaded');
  });
  assert.equal(await (await proxy.fetch(request)).text(), 'uploaded');
});
