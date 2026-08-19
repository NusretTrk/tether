"""
resolve_safe_path is the security boundary for /file and /files - every
failure mode (traversal, an absolute path elsewhere, a symlink escaping
root, a directory, a missing file) must come back as None, not a partial
success or a distinguishable error, so a probe request can't be used to
learn what exists outside the project root.
"""
import json
import os

import pytest

from tether.sources.files import list_recent_files, read_project_cwd, resolve_safe_path


# --- resolve_safe_path -----------------------------------------------

def test_plain_relative_path_inside_root_resolves(tmp_path):
    (tmp_path / "notes.md").write_text("hi", encoding="utf-8")
    result = resolve_safe_path(tmp_path, "notes.md")
    assert result == (tmp_path / "notes.md").resolve()


def test_nested_relative_path_inside_root_resolves(tmp_path):
    sub = tmp_path / "docs"
    sub.mkdir()
    (sub / "a.md").write_text("hi", encoding="utf-8")
    result = resolve_safe_path(tmp_path, "docs/a.md")
    assert result == (sub / "a.md").resolve()


def test_parent_traversal_is_refused(tmp_path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    try:
        assert resolve_safe_path(tmp_path, "../secret.txt") is None
    finally:
        outside.unlink()


def test_deep_traversal_is_refused(tmp_path):
    assert resolve_safe_path(tmp_path, "../../../../etc/passwd") is None


def test_absolute_path_outside_root_is_refused(tmp_path, tmp_path_factory):
    other = tmp_path_factory.mktemp("elsewhere")
    target = other / "file.txt"
    target.write_text("x", encoding="utf-8")
    assert resolve_safe_path(tmp_path, str(target)) is None


def test_absolute_path_actually_inside_root_still_resolves(tmp_path):
    f = tmp_path / "readme.md"
    f.write_text("hi", encoding="utf-8")
    assert resolve_safe_path(tmp_path, str(f)) == f.resolve()


def test_nonexistent_file_is_refused(tmp_path):
    assert resolve_safe_path(tmp_path, "does_not_exist.md") is None


def test_directory_is_refused_not_sent_as_a_file(tmp_path):
    (tmp_path / "subdir").mkdir()
    assert resolve_safe_path(tmp_path, "subdir") is None


def test_empty_or_blank_request_is_refused(tmp_path):
    assert resolve_safe_path(tmp_path, "") is None
    assert resolve_safe_path(tmp_path, "   ") is None


def test_bare_dotdot_is_refused(tmp_path):
    assert resolve_safe_path(tmp_path, "..") is None


def test_symlink_escaping_root_is_refused(tmp_path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere")
    secret = outside / "secret.txt"
    secret.write_text("nope", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted in this environment")
    assert resolve_safe_path(tmp_path, "link.txt") is None


# --- list_recent_files -------------------------------------------------

def test_missing_root_returns_empty(tmp_path):
    assert list_recent_files(tmp_path / "nope", (".md",), limit=10) == []


def test_filters_by_extension(tmp_path):
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    result = list_recent_files(tmp_path, (".md",), limit=10)
    assert result == [tmp_path / "a.md"]


def test_extension_match_is_case_insensitive(tmp_path):
    (tmp_path / "A.MD").write_text("x", encoding="utf-8")
    result = list_recent_files(tmp_path, (".md",), limit=10)
    assert result == [tmp_path / "A.MD"]


def test_skips_noise_directories(tmp_path):
    (tmp_path / "real.md").write_text("x", encoding="utf-8")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "hidden.md").write_text("x", encoding="utf-8")
    result = list_recent_files(tmp_path, (".md",), limit=10)
    assert result == [tmp_path / "real.md"]


def test_sorted_most_recent_first(tmp_path):
    import time
    old = tmp_path / "old.md"
    old.write_text("x", encoding="utf-8")
    time.sleep(0.05)
    new = tmp_path / "new.md"
    new.write_text("x", encoding="utf-8")
    result = list_recent_files(tmp_path, (".md",), limit=10)
    assert result == [new, old]


def test_respects_limit(tmp_path):
    for i in range(5):
        (tmp_path / f"f{i}.md").write_text("x", encoding="utf-8")
    result = list_recent_files(tmp_path, (".md",), limit=2)
    assert len(result) == 2


# --- read_project_cwd ---------------------------------------------------

def _write_jsonl(path, lines):
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")


def test_reads_cwd_from_first_line(tmp_path):
    p = tmp_path / "t.jsonl"
    _write_jsonl(p, [{"cwd": r"C:\Projects\foo"}])
    assert read_project_cwd(p) == __import__("pathlib").Path(r"C:\Projects\foo")


def test_finds_cwd_within_scan_window(tmp_path):
    p = tmp_path / "t.jsonl"
    _write_jsonl(p, [{"type": "meta"}, {"cwd": "/home/x/proj"}])
    assert read_project_cwd(p, max_lines=5) is not None


def test_cwd_beyond_scan_window_not_found(tmp_path):
    p = tmp_path / "t.jsonl"
    _write_jsonl(p, [{"type": "meta"}] * 3 + [{"cwd": "/home/x/proj"}])
    assert read_project_cwd(p, max_lines=2) is None


def test_malformed_lines_are_skipped(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("not json\n" + json.dumps({"cwd": "/home/x/proj"}), encoding="utf-8")
    assert read_project_cwd(p) is not None


def test_missing_file_returns_none(tmp_path):
    assert read_project_cwd(tmp_path / "nope.jsonl") is None


def test_no_cwd_field_anywhere_returns_none(tmp_path):
    p = tmp_path / "t.jsonl"
    _write_jsonl(p, [{"type": "meta"}, {"type": "other"}])
    assert read_project_cwd(p) is None
