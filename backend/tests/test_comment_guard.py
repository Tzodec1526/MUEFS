import importlib.util
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / "scripts" / "check_comments.py"
spec = importlib.util.spec_from_file_location("check_comments", GUARD)
check_comments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_comments)


def comments_in(source: str) -> list[str]:
    return [text for _, text in check_comments.yaml_findings(source)]


@pytest.mark.parametrize(("source", "comment"), [
    ("# refresh with pip freeze\nfastapi==0.162.0\n", "# refresh with pip freeze"),
    ("fastapi==0.162.0  # keep\n", "# keep"),
])
def test_a_comment_in_the_constraints_file_is_found(tmp_path, source, comment) -> None:
    pins = tmp_path / "constraints.txt"
    pins.write_text(source, encoding="utf-8")
    assert [text for _, text in check_comments.scan_file("constraints.txt", pins, [])] == [comment]


def test_plain_pins_and_other_text_files_pass(tmp_path) -> None:
    pins = tmp_path / "constraints.txt"
    pins.write_text('anyio==4.13.0\nuvloop==0.22.1; sys_platform != "win32"\n', encoding="utf-8")
    licence = tmp_path / "OFL.txt"
    licence.write_text("# Not a comment in a licence", encoding="utf-8")
    assert check_comments.scan_file("constraints.txt", pins, []) == []
    assert check_comments.scan_file("OFL.txt", licence, []) == []


@pytest.mark.parametrize(("line", "comment"), [
    ("run: echo hi # comment", "# comment"),
    ('run: echo "hello # world"', '# world"'),
    ("run: echo 'hello # world'", "# world'"),
    ('a: b - "c # d"', '# d"'),
    ('a: b, "c # d"', '# d"'),
    ("a: don't # real", "# real"),
    ('key: "hello # world" # real', "# real"),
    ("key: 'hello # world' # real", "# real"),
    ('- "a # b" # real', "# real"),
    ('a: "esc \\" # inside" # real', "# real"),
    ("a: 'it''s # inside' # real", "# real"),
    ('[ "a # b" ] # real', "# real"),
])
def test_a_comment_on_a_yaml_line_is_found(line: str, comment: str) -> None:
    assert comments_in(line) == [comment]


@pytest.mark.parametrize("line", [
    'key: "hello # world"',
    "key: 'hello # world'",
    'run: "echo hello # world"',
    "run: 'echo hello # world'",
    '- "a # b"',
    '- - "a # b"',
    '[ "a # b", "c # d" ]',
    '{ a: "b # c" }',
    '{"a":"b # c"}',
    '"a # b": c',
    "a: 'it''s # inside'",
    'a: "esc \\" # inside"',
    'a: !!str "b # c"',
    'a: &ref "b # c"',
    "a: b#c",
    "url: https://x/y#z",
])
def test_a_hash_inside_a_yaml_value_is_not_a_comment(line: str) -> None:
    assert comments_in(line) == []


def test_a_quoted_hash_in_a_block_scalar_is_not_a_comment() -> None:
    assert comments_in('run: |\n  echo "hello # world"\n') == []


@pytest.mark.parametrize(("source", "comment"), [
    ("run: |\n  # planted\n  echo hi\n", "# planted"),
    ("run: |\n  echo hi # planted\n", "# planted"),
    ('run: |\n  echo "a # b" # planted\n', "# planted"),
])
def test_a_shell_comment_in_a_block_scalar_is_found(source: str, comment: str) -> None:
    assert comments_in(source) == [comment]
