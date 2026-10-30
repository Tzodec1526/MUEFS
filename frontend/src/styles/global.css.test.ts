import { readdirSync, readFileSync } from 'node:fs';
import { expect, it } from 'vitest';

// Vitest serves stylesheet imports (even ?raw) as empty strings, so read the file itself.
const stylesDir = new URL('.', import.meta.url);
const read = (name: string): string => readFileSync(new URL(name, stylesDir), 'utf8');
const stylesheets = readdirSync(stylesDir).filter(name => name.endsWith('.css')).sort();
const css = stylesheets.filter(name => name !== 'global.css').map(read).join('\n');

const corpus = Object.values({
  ...import.meta.glob<string>(['../**/*.{ts,tsx}', '!../**/*.test.{ts,tsx}'], { query: '?raw', import: 'default', eager: true }),
  ...import.meta.glob<string>('../../index.html', { query: '?raw', import: 'default', eager: true }),
}).join('\n');

// Classes built at run time: `toast-${tone}`, and badge modifiers
// that come from API data (`status-badge ${filing.status}`, `age-badge ${age.level}`).
const DYNAMIC_PREFIXES = ['toast-'];
const DATA_MODIFIED = new Set(['status-badge', 'age-badge', 'flag-badge']);
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

it('styles every alert variant and status badge the pages render', () => {
  const alerts = new Set([...corpus.matchAll(/(?<![\w-])alert-[a-z]+(?![\w-])/g)].map(match => match[0]));
  expect([...alerts].sort()).toEqual(['alert-error', 'alert-info', 'alert-success', 'alert-warning']);
  const missing = [
    ...[...alerts].map(name => `.${name}`),
    ...BADGE_STATUSES.map(status => `.status-badge.${status}`),
  ].filter(selector => !definedSelectors.has(selector));
  expect(missing).toEqual([]);
});

it('keeps no rules for classes that nothing renders', () => {
  const unused = selectorLists.filter(list => splitSelectors(list)
    .every(selector => unrenderedClasses(selector).length > 0));
  expect(unused).toEqual([]);
});

const below600 = [...css.matchAll(/@media \(max-width: 599px\) \{([\s\S]*?)\n\}/g)].map(match => match[1]).join('\n');

it('imports every stylesheet from global.css, except the one the intake page loads itself', () => {
  const imports = [...read('global.css').matchAll(/^@import '\.\/([\w-]+\.css)';$/gm)].map(match => match[1]);
  expect(read('global.css').trim().split('\n')).toHaveLength(imports.length);
  expect([...imports].sort()).toEqual(stylesheets.filter(name => name !== 'global.css' && name !== 'intake.css'));
  expect(imports[0]).toBe('tokens.css');
  expect(stylesheets.length).toBeGreaterThan(10);
});

it('stacks the case search rows below 600 px instead of scrolling them sideways', () => {
  expect(below600).toMatch(/\.case-search-table tr \{\s+display: block;/);
  expect(below600).toMatch(/\.case-search-table td\[data-label\]::before \{\s+content: attr\(data-label\);/);
  expect(css).toMatch(/@media \(min-width: 600px\) and \(max-width: 760px\) \{\s+\.search-results table,/);
});

it('stacks the queue rows below 600 px and keeps Select all on screen there', () => {
  expect(below600).toMatch(/\.queue-list tbody tr \{\s+display: grid;/);
  expect(below600).toMatch(/\.queue-list td\[data-label\]::before \{\s+content: attr\(data-label\);/);
  expect(below600).toMatch(/\.queue-list thead \.th-checkbox \{\s+position: static;/);
  expect(below600).toMatch(/\.queue-select-all span \{\s+display: inline;/);
});

it('keeps the Menu button on the right of the main link, though it comes first in tab order', () => {
  expect(css).toMatch(/@media \(max-width: 768px\) \{[^@]*\.sidebar-toggle \{\s+display: block;\s+order: 1;/);
});

it('sentence-cases only status badges, whose values never reach the screen with an underscore', () => {
  const firstLetter = selectorLists.flatMap(splitSelectors).filter(selector => selector.includes('::first-letter'));
  expect(firstLetter).toEqual(['.status-badge::first-letter']);
  expect(corpus).not.toMatch(/status-badge[^\n]*>\{[\w.]*filing\.status\}/);
});

it('gives the court rule links in the wizard checklist a 24 px target', () => {
  expect(selectorLists.find(list => list.includes('.requirement-list a'))).toContain('td > a');
});

it('serves every font from this origin, in the weights the stylesheets use', () => {
  expect(read('../../index.html')).not.toMatch(/https?:/);
  const faces = [...css.matchAll(/@font-face \{([^}]*)\}/g)].map(match => match[1]);
  expect(faces).toHaveLength(3);
  for (const face of faces) {
    expect(face).toMatch(/font-family: 'Public Sans';/);
    expect(face).toMatch(/font-weight: 400 700;/);
    expect(face).toMatch(/font-display: swap;/);
    expect(face).toMatch(/src: url\('\.\.\/assets\/fonts\/public-sans-[\w-]+\.woff2'\) format\('woff2'\);/);
    expect(face).toMatch(/unicode-range: /);
  }
  const weights = new Set([...css.matchAll(/font-weight: (\w+);/g)].map(match => match[1]));
  expect([...weights].filter(weight => !['normal', '400', '500', '600', '700'].includes(weight))).toEqual([]);
  expect(css).not.toMatch(/font-style:\s*italic/);
  expect(css).not.toContain('IBM Plex');
});

it('sets dark text on the white notification panel inside the dark header', () => {
  expect(css).toMatch(/\.notification-panel \{[^}]*background: var\(--white\);[^}]*\scolor: var\(--ink\);/);
});

it('keeps every design token in one place', () => {
  const declared = stylesheets.filter(name => /^\s*--[\w-]+:/m.test(read(name)));
  expect(declared).toEqual(['tokens.css']);
});

it('keeps space between a docket document and its download button', () => {
  expect(css).toMatch(/\.docket-doc \{[^}]*display: inline-flex;[^}]*gap: 0\.5rem;/);
});

it('styles the heading of every empty state, whatever its level', () => {
  expect(definedSelectors.has('.empty-state h2')).toBe(true);
  expect(definedSelectors.has('.empty-state h3')).toBe(true);
});

it('hides the outline of a focused page heading only when the browser would not show a focus ring', () => {
  const rules = [...css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, , body]) => /outline:\s*(none|0)/.test(body))
    .flatMap(([, prelude]) => splitSelectors(prelude.trim()))
    .filter(selector => selector.startsWith('h1'));
  expect(rules).toEqual(['h1[tabindex="-1"]:focus:not(:focus-visible)']);
});
