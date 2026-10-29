/**
 * Headless Agent Hub UI smoke (Playwright).
 * Usage: node scripts/smoke-webmcp-ui.mjs [baseUrl]
 */
import { chromium } from 'playwright';

const base = process.argv[2] || process.env.MUEFS_BASE_URL || 'http://localhost:3000';
const failures = [];

function ok(name, cond, detail = '') {
  if (cond) console.log(`PASS ${name}`);
  else {
    console.log(`FAIL ${name} ${detail}`);
    failures.push(name);
  }
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
page.setDefaultTimeout(20000);
page.on('pageerror', err => ok('browser error', false, err.message));

try {
  await page.goto(`${base}/agent`, { waitUntil: 'networkidle' });
  ok('hub title', await page.getByRole('heading', { name: 'MUEFS Agent Hub' }).isVisible());
  ok('declarative section', await page.getByRole('heading', { name: 'Case search' }).isVisible());
  ok('prompts', await page.getByRole('heading', { name: 'Prompts' }).isVisible());

  const form = page.locator('form[toolname="search_cases_form"]');
  ok('declarative form', await form.isVisible());
  await form.getByLabel(/Party name/i).fill('Smith');
  await form.getByRole('button', { name: /^Search$/i }).click();
  await page.locator('.agent-declarative-hits li').first().waitFor({ state: 'visible', timeout: 15000 });
  ok('declarative hits', (await page.locator('.agent-declarative-hits li').count()) >= 1);

  await page.locator('.agent-declarative-hits li').first().getByRole('link', { name: 'Open' }).click();
  await page.waitForURL('**/cases/*');
  await page.locator('.case-detail-page').waitFor();
  ok('opens selected docket', await page.locator('.case-detail-page').isVisible());
} catch (err) {
  ok('uncaught', false, err instanceof Error ? err.message : String(err));
} finally {
  await browser.close();
}

console.log(`\nUI SMOKE fail=${failures.length}`);
process.exit(failures.length ? 1 : 0);
