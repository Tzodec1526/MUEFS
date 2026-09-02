#!/usr/bin/env node
/**
 * Drive the MUEFS demo the way a user does.
 * Invoke from the repo root:
 *   node .cursor/skills/verify-muefs/helpers/control-muefs.mjs <command>
 */
import { spawn, spawnSync } from 'node:child_process';
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const helperDir = dirname(fileURLToPath(import.meta.url));
const skillDir = resolve(helperDir, '..');
const repoRoot = resolve(skillDir, '../../..');
const runDir = join(skillDir, '.run');
const statePath = join(runDir, 'state.json');
const logPath = join(runDir, 'demo.log');
const profileDir = join(runDir, 'browser-profile');
const portPath = join(runDir, 'browser.port');
const daemonScript = join(helperDir, 'browser-daemon.mjs');
const FRONTEND = process.env.MUEFS_FRONTEND_URL || 'http://127.0.0.1:3000';
const API = process.env.MUEFS_API_URL || 'http://127.0.0.1:8000';
const LAUNCH_TIMEOUT_MS = 90_000;

function die(msg, code = 1) {
  console.error(msg);
  process.exit(code);
}

function loadState() {
  if (!existsSync(statePath)) return null;
  try {
    return JSON.parse(readFileSync(statePath, 'utf8'));
  } catch {
    return null;
  }
}

function saveState(state) {
  mkdirSync(runDir, { recursive: true });
  writeFileSync(statePath, JSON.stringify(state, null, 2), 'utf8');
}

function pidAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function httpGet(url, timeoutMs = 5000) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ac.signal });
    const text = await res.text();
    return { ok: res.ok, status: res.status, text };
  } catch (err) {
    return { ok: false, status: 0, text: '', error: err instanceof Error ? err.message : String(err) };
  } finally {
    clearTimeout(t);
  }
}

function pythonBin() {
  const candidates = process.platform === 'win32' ? ['python', 'py'] : ['python3', 'python'];
  for (const bin of candidates) {
    const r = spawnSync(bin, ['--version'], { encoding: 'utf8' });
    if (r.status === 0) return bin;
  }
  return null;
}

async function checkHealth() {
  const api = await httpGet(`${API}/health`);
  let apiJson = null;
  try {
    apiJson = JSON.parse(api.text);
  } catch {
    /* ignore */
  }
  const fe = await httpGet(`${FRONTEND}/`);
  const apiOk = api.ok && apiJson?.status === 'healthy' && apiJson?.service === 'muefs-api';
  const feOk = fe.ok && /Michigan Unified E-Filing System/i.test(fe.text);
  return { api, apiJson, apiOk, fe, feOk };
}

async function cmdLaunch() {
  mkdirSync(runDir, { recursive: true });
  const existing = loadState();
  const health = await checkHealth();
  if (health.apiOk && health.feOk) {
    if (existing?.owned && pidAlive(existing.pid)) {
      console.log(`already running pid=${existing.pid} frontend=${FRONTEND} api=${API}`);
      return;
    }
    if (process.env.MUEFS_VERIFY_ATTACH === '1') {
      saveState({
        owned: false,
        attached: true,
        frontend: FRONTEND,
        api: API,
        startedAt: new Date().toISOString(),
      });
      console.log(`attached to existing instance frontend=${FRONTEND} api=${API}`);
      return;
    }
    die(
      `Ports ${FRONTEND} / ${API} are already serving MUEFS, but this run did not start them. ` +
        'Refuse to double-drive a shared instance. Stop that demo, or set MUEFS_VERIFY_ATTACH=1 to attach.',
    );
  }
  if (health.api.ok || health.fe.ok) {
    die(
      `Partial occupancy: api_ok=${health.api.ok} frontend_ok=${health.fe.ok}. ` +
        'Free ports 8000 and 3000 before launching verification.',
    );
  }

  const py = pythonBin();
  if (!py) die('python is not on PATH');
  const script = join(repoRoot, 'backend', 'run_demo.py');
  if (!existsSync(script)) die(`missing ${script}`);

  const logFd = openSync(logPath, 'w');
  const child = spawn(py, [script], {
    cwd: join(repoRoot, 'backend'),
    env: { ...process.env, PYTHONUNBUFFERED: '1', VITE_ALLOW_DEMO_MODE: 'true' },
    stdio: ['ignore', logFd, logFd],
    detached: true,
    windowsHide: true,
  });
  closeSync(logFd);
  child.unref();

  saveState({
    owned: true,
    pid: child.pid,
    frontend: FRONTEND,
    api: API,
    startedAt: new Date().toISOString(),
  });

  const deadline = Date.now() + LAUNCH_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (!pidAlive(child.pid)) {
      die(`demo process exited before ready. See ${logPath}`);
    }
    const h = await checkHealth();
    if (h.apiOk && h.feOk) {
      console.log(`ready pid=${child.pid} frontend=${FRONTEND} api=${API}`);
      return;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  killOwned(child.pid);
  die(`timed out waiting for ${FRONTEND} and ${API}/health. See ${logPath}`);
}

async function cmdDoctor() {
  const state = loadState();
  const health = await checkHealth();
  const ownedAlive = Boolean(state?.owned && pidAlive(state.pid));
  const attach = Boolean(state?.attached);
  const lines = [
    `frontend ${FRONTEND} ok=${health.feOk} status=${health.fe.status}`,
    `api ${API}/health ok=${health.apiOk} body=${health.api.text || health.api.error || ''}`,
    `state owned=${Boolean(state?.owned)} attached=${attach} pid=${state?.pid ?? 'none'} pid_alive=${ownedAlive}`,
  ];
  for (const line of lines) console.log(line);
  if (!health.apiOk || !health.feOk) {
    die('doctor: instance is not worth driving');
  }
  if (!ownedAlive && !attach && !process.env.MUEFS_VERIFY_ATTACH) {
    die(
      'doctor: healthy ports, but this run does not own the process. ' +
        'Launch via control-muefs launch, or set MUEFS_VERIFY_ATTACH=1.',
    );
  }
  console.log('doctor: ok');
}

function killOwned(pid) {
  if (!pid) return;
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { encoding: 'utf8' });
  } else {
    try {
      process.kill(-pid, 'SIGTERM');
    } catch {
      try {
        process.kill(pid, 'SIGTERM');
      } catch {
        /* already gone */
      }
    }
  }
}

function cmdCleanup() {
  const state = loadState();
  if (state?.browserPid) {
    killOwned(state.browserPid);
    console.log(`stopped browser pid=${state.browserPid}`);
  }
  if (state?.owned && state.pid) {
    killOwned(state.pid);
    console.log(`stopped demo pid=${state.pid}`);
  } else if (state?.attached) {
    console.log('attached instance left running (cleanup does not kill what we did not start)');
  } else {
    console.log('no owned demo instance');
  }
  for (const p of [profileDir, portPath, statePath, join(runDir, 'browser.ws')]) {
    if (existsSync(p)) rmSync(p, { recursive: true, force: true });
  }
  console.log('cleanup: run state removed; artifacts preserved');
}

function parseFlags(argv) {
  const flags = {};
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (!next || next.startsWith('--')) flags[key] = true;
      else {
        flags[key] = next;
        i++;
      }
    } else rest.push(a);
  }
  return { flags, rest };
}

function resolveOut(p) {
  if (!p) die('missing --path');
  const abs = isAbsolute(p) ? p : resolve(skillDir, p);
  mkdirSync(dirname(abs), { recursive: true });
  return abs;
}

async function ensureBrowserServer() {
  mkdirSync(runDir, { recursive: true });
  const state = loadState() || {};
  if (state.browserPid && pidAlive(state.browserPid) && existsSync(portPath)) {
    const port = readFileSync(portPath, 'utf8').trim();
    const health = await httpGet(`http://127.0.0.1:${port}/health`);
    if (health.ok) return port;
  }
  if (state.browserPid && pidAlive(state.browserPid)) killOwned(state.browserPid);
  if (existsSync(portPath)) rmSync(portPath, { force: true });
  const logFd = openSync(join(runDir, 'browser-daemon.log'), 'w');
  const child = spawn(process.execPath, [daemonScript], {
    cwd: repoRoot,
    env: process.env,
    stdio: ['ignore', logFd, logFd],
    detached: true,
    windowsHide: true,
  });
  closeSync(logFd);
  child.unref();
  saveState({ ...loadState(), browserPid: child.pid });
  const deadline = Date.now() + 45_000;
  while (Date.now() < deadline) {
    if (existsSync(portPath)) {
      const port = readFileSync(portPath, 'utf8').trim();
      const health = await httpGet(`http://127.0.0.1:${port}/health`);
      if (health.ok) return port;
    }
    if (!pidAlive(child.pid)) die(`browser daemon exited. See ${join(runDir, 'browser-daemon.log')}`);
    await new Promise((r) => setTimeout(r, 200));
  }
  die('timed out starting browser daemon');
}

async function cmdBrowser(argv) {
  const sub = argv[0];
  const { flags, rest } = parseFlags(argv.slice(1));
  if (!sub) die('browser needs a subcommand: goto | click | fill | wait | expect | snapshot | screenshot');
  if (flags.path) flags.path = resolveOut(flags.path);
  const port = await ensureBrowserServer();
  const res = await fetch(`http://127.0.0.1:${port}/cmd`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ sub, flags, rest }),
  });
  const body = await res.json();
  if (!body.ok) die(body.error || 'browser command failed');
  console.log(body.msg);
}

async function cmdApi(argv) {
  const sub = argv[0];
  const { flags, rest } = parseFlags(argv.slice(1));
  if (sub !== 'get') die('api supports: get <path>');
  const pathOrUrl = rest[0];
  if (!pathOrUrl) die('api get needs a path');
  const url = /^https?:/i.test(pathOrUrl) ? pathOrUrl : `${API}${pathOrUrl.startsWith('/') ? '' : '/'}${pathOrUrl}`;
  const res = await httpGet(url, 15_000);
  if (flags.path) writeFileSync(resolveOut(flags.path), res.text, 'utf8');
  console.log(`status=${res.status}`);
  if (!flags.path) console.log(res.text);
  if (!res.ok) die(`api get failed: ${url}`);
}

const argv = process.argv.slice(2);
const cmd = argv[0];
if (!cmd || cmd === '-h' || cmd === '--help') {
  console.log(`control-muefs — drive the MUEFS demo filing portal

Usage (repo root):
  node .cursor/skills/verify-muefs/helpers/control-muefs.mjs launch
  node .cursor/skills/verify-muefs/helpers/control-muefs.mjs doctor
  node .cursor/skills/verify-muefs/helpers/control-muefs.mjs cleanup
  node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=attorney
  node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Search"
  node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser fill --label "Party Name" --value Smith
  node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Results"
  node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser snapshot --aria --path artifacts/case-search/results.aria.txt
  node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser screenshot --path artifacts/case-search/results.png
  node .cursor/skills/verify-muefs/helpers/control-muefs.mjs api get /api/v1/cases/search?party_name=Smith --path artifacts/case-search/search.json
`);
  process.exit(0);
}

try {
  if (cmd === 'launch') await cmdLaunch();
  else if (cmd === 'doctor') await cmdDoctor();
  else if (cmd === 'cleanup') cmdCleanup();
  else if (cmd === 'browser') await cmdBrowser(argv.slice(1));
  else if (cmd === 'api') await cmdApi(argv.slice(1));
  else die(`unknown command: ${cmd}`);
} catch (err) {
  die(err instanceof Error ? err.stack || err.message : String(err));
}
