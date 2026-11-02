const path = require('path');
const ts = require(path.join(__dirname, '..', 'frontend', 'node_modules', 'typescript'));

const COMMENT = 1;
const input = require('fs').readFileSync(0, 'utf8');
const scripts = JSON.parse(input);
const texts = Object.fromEntries(scripts.map(script => [script.name, script.text]));
const names = Object.keys(texts);

const service = ts.createLanguageService({
  getScriptFileNames: () => names,
  getScriptVersion: () => '1',
  getScriptSnapshot: name => (texts[name] === undefined ? undefined : ts.ScriptSnapshot.fromString(texts[name])),
  getCurrentDirectory: () => process.cwd(),
  getCompilationSettings: () => ({ allowJs: true, jsx: ts.JsxEmit.Preserve }),
  getDefaultLibFileName: options => ts.getDefaultLibFilePath(options),
  fileExists: name => texts[name] !== undefined,
  readFile: name => texts[name],
});

function commentEnd(text, start, length) {
  if (text.startsWith('/*', start)) {
    const close = text.indexOf('*/', start + 2);
    return close < 0 ? text.length : close + 2;
  }
  if (text.startsWith('//', start) || text.startsWith('#!', start)) {
    const newline = text.indexOf('\n', start);
    return newline < 0 ? text.length : newline;
  }
  return start + length;
}

const found = [];
for (const script of scripts) {
  const { name, text } = script;
  if (text.startsWith('#!')) found.push({ name: script.file ?? name, line: 1, text: text.split('\n', 1)[0] });
  const { spans } = service.getEncodedSyntacticClassifications(name, { start: 0, length: text.length });
  let covered = 0;
  for (let index = 0; index < spans.length; index += 3) {
    const [start, length, kind] = [spans[index], spans[index + 1], spans[index + 2]];
    if (kind !== COMMENT || start < covered) continue;
    covered = commentEnd(text, start, length);
    const line = text.slice(0, start).split('\n').length + (script.offset ?? 0);
    found.push({ name: script.file ?? name, line, text: text.slice(start, covered) });
  }
}
process.stdout.write(JSON.stringify(found));
