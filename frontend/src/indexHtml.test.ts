import { expect, it } from 'vitest';

const [html] = Object.values(import.meta.glob<string>('../index.html', { query: '?raw', import: 'default', eager: true }));

it('runs the runtime configuration before the app, without blocking the parser', () => {
  const scripts = [...new DOMParser().parseFromString(html, 'text/html').scripts];

  expect(scripts.map(script => script.getAttribute('src'))).toEqual(['/config.js', '/src/main.tsx']);
  expect(scripts[0].defer).toBe(true);
  expect(scripts[0].hasAttribute('async')).toBe(false);
  expect(scripts[0].type).toBe('');
  expect(scripts[1].type).toBe('module');
  expect(scripts[1].hasAttribute('async')).toBe(false);
});
