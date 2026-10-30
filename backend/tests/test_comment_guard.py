import importlib.util
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / "scripts" / "check_comments.py"
spec = importlib.util.spec_from_file_location("check_comments", GUARD)
check_comments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_comments)


def comments_in(source: str) -> list[str]:
    return [text for _, text in check_comments.yaml_findings(source)]


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
