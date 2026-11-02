import { randomBytes, timingSafeEqual } from 'node:crypto';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const helperDir = dirname(fileURLToPath(import.meta.url));
const skillDir = resolve(helperDir, '..');
const repoRoot = resolve(skillDir, '../../..');
const runDir = join(skillDir, '.run');
const artifactsDir = join(skillDir, 'artifacts');
mkdirSync(runDir, { recursive: true });
const token = randomBytes(32).toString('hex');
writeFileSync(join(runDir, 'browser.token'), token, { encoding: 'utf8', mode: 0o600 });

const require = createRequire(import.meta.url);
const { chromium } = require(join(repoRoot, 'frontend', 'node_modules', 'playwright'));
const headed = process.env.MUEFS_VERIFY_HEADED === '1';
const FRONTEND = process.env.MUEFS_FRONTEND_URL || 'http://127.0.0.1:3000';

const browser = await chromium.launch({ headless: !headed });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.setDefaultTimeout(20_000);

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function outputPath(out) {
  if (!out) throw new Error('missing --path');
  const abs = resolve(skillDir, out);
  const inside = relative(artifactsDir, abs);
  if (!inside || isAbsolute(inside) || inside === '..' || inside.startsWith(`..${sep}`)) {
    throw new Error('--path must be inside the artifacts/ folder of this skill');
  }
  mkdirSync(dirname(abs), { recursive: true });
  return abs;
}

function authorized(req) {
  const provided = Buffer.from(String(req.headers['x-verify-token'] || ''));
  const expected = Buffer.from(token);
  return req.headers['content-type'] === 'application/json'
    && provided.length === expected.length && timingSafeEqual(provided, expected);
}

function locator(flags) {
  if (flags.label) return page.getByLabel(String(flags.label), { exact: Boolean(flags.exact) });
  if (flags.role) {
    const opts = {};
    if (flags.name) {
      opts.name = flags.exact ? String(flags.name) : new RegExp(escapeRegExp(String(flags.name)), 'i');
      opts.exact = Boolean(flags.exact);
    }
    return page.getByRole(String(flags.role), opts);
  }
  throw new Error('need --role/--name or --label');
}

async function run(cmd) {
  const { sub, flags = {}, rest = [] } = cmd;
  if (sub === 'goto') {
    const pathOrUrl = rest[0] || flags.path || '/';
    const url = /^https?:/i.test(pathOrUrl)
      ? pathOrUrl
      : `${FRONTEND}${pathOrUrl.startsWith('/') ? '' : '/'}${pathOrUrl}`;
    await page.goto(url, { waitUntil: 'networkidle' });
    return `goto ${page.url()}`;
  }
  if (sub === 'click') {
    await locator(flags).first().click();
    await page.waitForLoadState('networkidle');
    return `clicked ${page.url()}`;
  }
  if (sub === 'fill') {
    if (flags.value === undefined) throw new Error('fill needs --value');
    await locator(flags).first().fill(String(flags.value));
    return 'filled';
  }
  if (sub === 'press') {
    const key = flags.key || rest[0];
    if (!key) throw new Error('press needs --key');
    await page.keyboard.press(String(key));
    return `pressed ${key}`;
  }
  if (sub === 'wait' || sub === 'expect') {
    await locator(flags).first().waitFor({ state: 'visible' });
    return 'visible';
  }
  if (sub === 'snapshot') {
    const abs = outputPath(flags.path);
    let text;
    try {
      text = await page.locator('body').ariaSnapshot();
    } catch {
      text = await page.locator('#main-content, main, body').first().innerText();
    }
    writeFileSync(abs, text, 'utf8');
    return `wrote ${abs}`;
  }
  if (sub === 'screenshot') {
    const abs = outputPath(flags.path);
    await page.screenshot({ path: abs, fullPage: Boolean(flags.fullpage) });
    return `wrote ${abs}`;
  }
  throw new Error(`unknown browser subcommand: ${sub}`);
}

const server = createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, url: page.url() }));
    return;
  }
  if (req.method !== 'POST' || req.url !== '/cmd') {
    res.writeHead(404);
    res.end('not found');
    return;
  }
  if (!authorized(req)) {
    res.writeHead(403);
    res.end('forbidden');
    return;
  }
  const chunks = [];
  for await (const c of req) chunks.push(c);
  try {
    const cmd = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
    const msg = await run(cmd);
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, msg, url: page.url() }));
  } catch (err) {
    res.writeHead(500, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: false, error: err instanceof Error ? err.message : String(err) }));
  }
});

server.listen(0, '127.0.0.1', () => {
  const { port } = server.address();
  writeFileSync(join(runDir, 'browser.port'), String(port), 'utf8');
});
