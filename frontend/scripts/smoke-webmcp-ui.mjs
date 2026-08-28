/**
 * Headless Agent Hub UI smoke (Playwright).
 * Usage: node scripts/smoke-webmcp-ui.mjs [baseUrl]
 */
import { chromium } from 'playwright';

const base = process.argv[2] || process.env.MUEFS_BASE_URL || 'http://127.0.0.1:8010';
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

try {
  await page.goto(`${base}/agent`, { waitUntil: 'networkidle' });
  ok('hub title', await page.getByRole('heading', { name: 'MUEFS Agent Hub' }).isVisible());
  ok('declarative section', await page.getByText(/Declarative WebMCP/i).isVisible());
  ok('flagship section', await page.getByText(/Flagship demos/i).isVisible());
  ok('judge prompts', await page.getByText(/Judge prompts/i).isVisible());

  const form = page.locator('form[toolname="search_cases"]');
  ok('declarative form', await form.isVisible());
  await form.getByLabel(/Party name/i).fill('Smith');
  await form.getByRole('button', { name: /Search \(declarative\)/i }).click();
  await page.locator('.agent-declarative-hits li').first().waitFor({ state: 'visible', timeout: 15000 });
  ok('declarative hits', (await page.locator('.agent-declarative-hits li').count()) >= 1);

  await page.getByRole('button', { name: /Attorney · Smith motion/i }).click();
  await page.locator('.agent-demo-steps code').filter({ hasText: 'attorney_motion_workflow' }).waitFor({
    state: 'visible',
    timeout: 20000,
  });
  const attorneyDetail = await page
    .locator('.agent-demo-steps li.ok')
    .filter({ hasText: 'attorney_motion_workflow' })
    .innerText();
  ok('attorney workflow', /required docs/.test(attorneyDetail), attorneyDetail);
  ok('attorney has MCR data', !/0 required docs · 0 motion/.test(attorneyDetail), attorneyDetail);
  ok('open result path', await page.getByRole('button', { name: /Open result path/i }).isVisible());

  await page.getByRole('button', { name: /Clerk · triage/i }).click();
  await page.locator('.agent-demo-steps code').filter({ hasText: 'clerk_triage_workflow' }).waitFor({
    state: 'visible',
    timeout: 20000,
  });
  ok('clerk workflow', true);

  await page.getByRole('button', { name: /SRL · explain MCR/i }).click();
  await page.locator('.agent-demo-steps code').filter({ hasText: 'explain_mcr_for_filing' }).waitFor({
    state: 'visible',
    timeout: 20000,
  });
  const srlDetail = await page
    .locator('.agent-demo-steps li.ok')
    .filter({ hasText: 'explain_mcr_for_filing' })
    .innerText();
  ok('srl has MCR data', !/0 required docs/.test(srlDetail), srlDetail);
} catch (err) {
  ok('uncaught', false, err instanceof Error ? err.message : String(err));
} finally {
  await browser.close();
}

console.log(`\nUI SMOKE fail=${failures.length}`);
process.exit(failures.length ? 1 : 0);
