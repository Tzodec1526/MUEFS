import { expect, it } from 'vitest';

// Vitest serves stylesheet imports (even ?raw) as empty strings, so read the file itself.
const fsModule = 'node:fs';
const { readFileSync } = await import(/* @vite-ignore */ fsModule);
const css: string = readFileSync(new URL('./global.css', import.meta.url), 'utf8');

const corpus = Object.values({
  ...import.meta.glob<string>(['../**/*.{ts,tsx}', '!../**/*.test.{ts,tsx}'], { query: '?raw', import: 'default', eager: true }),
  ...import.meta.glob<string>('../../index.html', { query: '?raw', import: 'default', eager: true }),
}).join('\n');

// Classes built at run time: `toast-${tone}`, `mifile-comparison--${variant}`, and badge modifiers
// that come from API data (`status-badge ${filing.status}`, `age-badge ${age.level}`).
const DYNAMIC_PREFIXES = ['toast-', 'mifile-comparison--'];
const DATA_MODIFIED = new Set(['status-badge', 'age-badge', 'flag-badge', 'req-badge']);
// Filing statuses (backend FilingStatus) and case statuses (backend CaseStatus) shown on status badges.
const BADGE_STATUSES = [
  'draft', 'submitted', 'under_review', 'accepted', 'rejected', 'returned', 'served',
  'open', 'closed', 'dismissed', 'pending',
];

/** Selector lists of the style rules, including rules inside @media blocks. */
const selectorLists = [...css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{[^{}]*\}/g)]
  .map(match => match[1].trim())
  .filter(prelude => !prelude.startsWith('@'));

function splitSelectors(list: string): string[] {
  const selectors: string[] = [];
  let depth = 0, start = 0;
  [...list].forEach((char, index) => {
    if (char === '(') depth++;
    else if (char === ')') depth--;
    else if (char === ',' && depth === 0) { selectors.push(list.slice(start, index)); start = index + 1; }
  });
  selectors.push(list.slice(start));
  return selectors.map(selector => selector.trim());
}

const definedSelectors = new Set(selectorLists.flatMap(splitSelectors));

function rendered(name: string): boolean {
  return DYNAMIC_PREFIXES.some(prefix => name.startsWith(prefix))
    || new RegExp(`(?<![\\w-])${name}(?![\\w-])`).test(corpus);
}

/** Classes a selector requires that nothing renders. */
function unrenderedClasses(selector: string): string[] {
  const required = selector.replace(/:not\([^)]*\)/g, '').replace(/\[[^\]]*\]/g, '');
  return required.split(/[\s>+~]+/).flatMap(compound => {
    const classes = [...compound.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)].map(match => match[1]);
    const dataModified = classes.some(name => DATA_MODIFIED.has(name));
    return classes.filter(name => !(dataModified && !DATA_MODIFIED.has(name)) && !rendered(name));
  });
}

it('styles every alert variant, status badge and muted text the pages render', () => {
  const alerts = new Set([...corpus.matchAll(/(?<![\w-])alert-[a-z]+(?![\w-])/g)].map(match => match[0]));
  expect([...alerts].sort()).toEqual(['alert-error', 'alert-info', 'alert-success', 'alert-warning']);
  const missing = [
    ...[...alerts].map(name => `.${name}`),
    ...BADGE_STATUSES.map(status => `.status-badge.${status}`),
    '.text-muted',
  ].filter(selector => !definedSelectors.has(selector));
  expect(missing).toEqual([]);
});

it('keeps no rules for classes that nothing renders', () => {
  const unused = selectorLists.filter(list => splitSelectors(list)
    .every(selector => unrenderedClasses(selector).length > 0));
  expect(unused).toEqual([]);
});

it('hides the outline of a focused page heading only when the browser would not show a focus ring', () => {
  const rules = [...css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, , body]) => /outline:\s*(none|0)/.test(body))
    .flatMap(([, prelude]) => splitSelectors(prelude.trim()))
    .filter(selector => selector.startsWith('h1'));
  expect(rules).toEqual(['h1[tabindex="-1"]:focus:not(:focus-visible)']);
});
