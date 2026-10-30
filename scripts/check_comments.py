import ast
import io
import json
import subprocess
import sys
import textwrap
import tokenize
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "scripts" / "comment-allowlist.json"
SCRIPT_SCANNER = ROOT / "scripts" / "check-comments.cjs"
SCRIPT_SUFFIXES = {".ts", ".tsx", ".js", ".mjs", ".cjs"}
NO_COMMENT_SYNTAX = {".md", ".pdf", ".woff2", ".cdb", ".txt"}
NO_COMMENT_NAMES = {"LICENSE"}
LINE_START_NAMES = {".gitignore", ".dockerignore", ".gitattributes"}
LINE_START_SUFFIXES = {".conf"}
SHELL_WORD_BREAKS = " \t;&|("


def comment_tokens(source):
    return [
        token for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    ]


def embedded_python_findings(text, line):
    source = textwrap.dedent(text)
    try:
        ast.parse(source)
        tokens = comment_tokens(source)
    except (SyntaxError, ValueError, tokenize.TokenError):
        return []
    return [(line + token.start[0], "in embedded source: " + token.string) for token in tokens]


def python_findings(source, offset=0):
    found = [(token.start[0] + offset, token.string) for token in comment_tokens(source)]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            found.append((node.lineno + offset, "string statement: " + node.value.value[:60]))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "\n" in node.value:
            found += embedded_python_findings(node.value, node.lineno + offset)
    return found


def skip_template_expression(source, start):
    depth = 0
    index = start
    quote = None
    while index < len(source):
        char = source[index]
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return index


def mako_findings(source):
    found = []
    code = []
    index = 0
    line = 1
    while index < len(source):
        if source.startswith("<%doc>", index):
            found.append((line, "<%doc>"))
        if source.startswith("<%", index) and not source.startswith("<%doc>", index):
            end = source.find("%>", index)
            end = len(source) if end < 0 else end
            body = source[index + 2:end].lstrip("!")
            found += python_findings(textwrap.dedent(body), line - 1)
            line += source.count("\n", index, end)
            code.append("\n" * source.count("\n", index, end))
            index = end + 2
            continue
        if source.startswith("${", index):
            end = skip_template_expression(source, index + 1)
            code.append("_")
            index = end
            continue
        at_line_start = index == 0 or source[index - 1] == "\n"
        if at_line_start and source[index:].lstrip(" \t").startswith("##"):
            end = source.find("\n", index)
            end = len(source) if end < 0 else end
            found.append((line, source[index:end].strip()))
            index = end
            continue
        if source[index] == "\n":
            line += 1
        code.append(source[index])
        index += 1
    return found + python_findings("".join(code))


def shell_findings(text, first_line=1):
    found = []
    quote = None
    line = first_line
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\n":
            line += 1
        elif char == "\\" and quote != "'":
            index += 1
            if text[index:index + 1] == "\n":
                line += 1
        elif quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or text[index - 1] in SHELL_WORD_BREAKS + "\n"):
            end = text.find("\n", index)
            end = len(text) if end < 0 else end
            found.append((line, text[index:end]))
            index = end - 1
        index += 1
    return found


def yaml_comment_column(line):
    quote = None
    node_start = True
    flow_depth = 0
    index = 0
    while index < len(line):
        char = line[index]
        following = line[index + 1:index + 2]
        if quote:
            if quote == '"' and char == "\\":
                index += 1
            elif char == quote and quote == "'" and following == "'":
                index += 1
            elif char == quote:
                quote = None
        elif char == "#" and (index == 0 or line[index - 1] in " \t"):
            return index
        elif char == ":" and (flow_depth or following in ("", " ", "\t")):
            node_start = True
        elif char == "," and flow_depth:
            node_start = True
        elif char in "[{" and (node_start or flow_depth):
            flow_depth += 1
            node_start = True
        elif char in "]}" and flow_depth:
            flow_depth -= 1
        elif node_start and char in "-?" and following in ("", " ", "\t"):
            pass
        elif node_start and char in "!&":
            while index + 1 < len(line) and line[index + 1] not in " \t":
                index += 1
        elif node_start and char in "\"'":
            quote = char
            node_start = False
        elif char not in " \t":
            node_start = False
        index += 1
    return None


def starts_block_scalar(line):
    stripped = line.rstrip()
    tail = stripped.rsplit(" ", 1)[-1]
    if tail[:1] not in ("|", ">") or len(tail) == len(stripped):
        return False
    if any(char not in "+-123456789" for char in tail[1:]):
        return False
    return stripped[:-len(tail)].rstrip().endswith((":", "-"))


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def yaml_findings(source):
    found = []
    lines = source.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        column = yaml_comment_column(line)
        if column is not None:
            found.append((index + 1, line[column:]))
            line = line[:column]
        index += 1
        if line.strip() and starts_block_scalar(line):
            start = index
            indent = indent_of(line)
            while index < len(lines) and (
                not lines[index].strip() or indent_of(lines[index]) > indent
            ):
                index += 1
            found += shell_findings("\n".join(lines[start:index]), start + 1)
    return found


def toml_findings(source):
    found = []
    line = 1
    index = 0
    delimiter = None
    while index < len(source):
        if delimiter:
            if source.startswith(delimiter, index):
                index += len(delimiter)
                delimiter = None
                continue
            if source[index] == "\\" and delimiter[0] == '"':
                index += 1
        elif source.startswith(('"""', "'''"), index):
            delimiter = source[index:index + 3]
            index += 3
            continue
        elif source[index] in "\"'":
            delimiter = source[index]
        elif source[index] == "#":
            end = source.find("\n", index)
            end = len(source) if end < 0 else end
            found.append((line, source[index:end]))
            index = end
            continue
        if source[index:index + 1] == "\n":
            line += 1
        index += 1
    return found


def css_findings(source, first_line=1):
    found = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char in "\"'":
            index += 1
            while index < length and source[index] != char and source[index] != "\n":
                index += 2 if source[index] == "\\" else 1
            index += 1
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = length if end < 0 else end + 2
            found.append((first_line + source.count("\n", 0, index), source[index:end]))
            index = end
        elif source[index:index + 4].lower() == "url(" and (
            index == 0 or not (source[index - 1].isalnum() or source[index - 1] in "-_")
        ):
            index += 4
            while index < length and source[index] in " \t\n":
                index += 1
            if index < length and source[index] not in "\"'":
                while index < length and source[index] != ")":
                    index += 2 if source[index] == "\\" else 1
        else:
            index += 1
    return found


class HtmlScanner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.found = []
        self.raw_tag = None
        self.raw_has_src = False
        self.scripts = []

    def handle_comment(self, data):
        self.found.append((self.getpos()[0], f"<!--{data}-->"))

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.raw_tag = tag
            self.raw_has_src = any(name == "src" for name, _ in attrs)

    def handle_endtag(self, tag):
        if tag == self.raw_tag:
            self.raw_tag = None

    def handle_data(self, data):
        line = self.getpos()[0]
        if self.raw_tag == "style":
            self.found += css_findings(data, line)
        elif self.raw_tag == "script" and not self.raw_has_src:
            self.scripts.append((line, data))


def html_findings(source):
    scanner = HtmlScanner()
    scanner.feed(source)
    scanner.close()
    return scanner.found, scanner.scripts


def line_start_findings(source, markers):
    return [
        (number, line.strip()) for number, line in enumerate(source.split("\n"), 1)
        if line.lstrip().startswith(markers)
    ]


def dockerfile_findings(source):
    found = line_start_findings(source, ("#",))
    code = "\n".join(
        "" if line.lstrip().startswith("#") else line for line in source.split("\n")
    )
    return found + shell_findings(code)


def env_findings(source):
    return [
        (number, text) for number, line in enumerate(source.split("\n"), 1)
        for _, text in shell_findings(line, number)
    ]


def json_findings(source):
    try:
        json.loads(source)
    except ValueError as error:
        return [(error.lineno, f"not plain JSON: {error.msg}")]
    return []


def is_ignore_file(path):
    return path.name in LINE_START_NAMES or path.name.endswith(".dockerignore")


def scan_file(name, path, scripts):
    suffix = path.suffix
    if path.name in NO_COMMENT_NAMES or suffix in NO_COMMENT_SYNTAX:
        return []
    if suffix in SCRIPT_SUFFIXES:
        scripts.append({"name": name, "text": path.read_text(encoding="utf-8")})
        return []
    source = path.read_text(encoding="utf-8")
    if suffix == ".py":
        return python_findings(source)
    if suffix == ".mako":
        return mako_findings(source)
    if suffix == ".css":
        return css_findings(source)
    if suffix in (".yml", ".yaml"):
        return yaml_findings(source)
    if suffix == ".toml":
        return toml_findings(source)
    if suffix == ".json":
        return json_findings(source)
    if suffix == ".ini":
        return line_start_findings(source, ("#", ";"))
    if suffix in LINE_START_SUFFIXES or is_ignore_file(path):
        return line_start_findings(source, ("#",))
    if path.name == "Dockerfile":
        return dockerfile_findings(source)
    if path.name.startswith(".env"):
        return env_findings(source)
    if suffix == ".html":
        found, inline = html_findings(source)
        for number, (line, text) in enumerate(inline):
            scripts.append({
                "name": f"{name}.inline-{number}.ts", "file": name, "text": text, "offset": line - 1,
            })
        return found
    return [(0, "no comment tokenizer for this file type")]


def tracked_files():
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    return sorted(name for name in listing.split("\0") if name and (ROOT / name).is_file())


def script_findings(scripts):
    done = subprocess.run(
        ["node", str(SCRIPT_SCANNER)], input=json.dumps(scripts), cwd=ROOT,
        capture_output=True, encoding="utf-8",
    )
    if done.returncode != 0:
        raise SystemExit(f"script scanner failed: {done.stderr}")
    return json.loads(done.stdout)


def main():
    allowed = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    missing_reason = [entry for entry in allowed if not entry.get("reason")]
    findings = []
    scripts = []
    files = tracked_files()
    for name in files:
        try:
            found = scan_file(name, ROOT / name, scripts)
        except (SyntaxError, ValueError) as error:
            found = [(0, f"could not tokenize: {error}")]
        findings += [(name, line, text) for line, text in found]
    findings += [
        (row["name"], row["line"], row["text"]) for row in script_findings(scripts)
    ]
    used = set()
    reported = []
    for name, line, text in findings:
        match = next(
            (index for index, entry in enumerate(allowed)
             if entry["file"] == name and entry["text"] == text),
            None,
        )
        if match is None:
            reported.append((name, line, text))
        else:
            used.add(match)
    stale = [entry for index, entry in enumerate(allowed) if index not in used]
    for name, line, text in reported:
        first = text.splitlines()[0] if text else ""
        print(f"{name}:{line}: {first[:100]}")
    for entry in stale:
        print(f"allowlist entry matches nothing: {entry['file']}: {entry['text']}")
    for entry in missing_reason:
        print(f"allowlist entry has no reason: {entry['file']}: {entry.get('text')}")
    if reported or stale or missing_reason:
        print(f"{len(reported)} comments found. Remove them, or fix what made them necessary.")
        return 1
    print(f"No comments in {len(files)} files. Allowlist entries: {len(allowed)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
