"""
find_active_antigravity_transcript mirrors find_active_transcript's
freshest-file logic, just under a different directory shape
(~/.gemini/<product>/brain/<uuid>/.system_generated/logs/transcript.jsonl,
confirmed against real files on this machine under both the
"antigravity" and "antigravity-ide" product directory names).
"""
import time

from tether.sources.discovery import find_active_antigravity_transcript, find_active_transcript


def _make_transcript(root, product, uuid):
    path = root / product / "brain" / uuid / ".system_generated" / "logs" / "transcript.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"type": "USER_INPUT"}\n', encoding="utf-8")
    return path


def test_missing_root_returns_none(tmp_path):
    assert find_active_antigravity_transcript(tmp_path / "does_not_exist") is None


def test_no_transcripts_returns_none(tmp_path):
    (tmp_path / "antigravity").mkdir()
    assert find_active_antigravity_transcript(tmp_path) is None


def test_picks_the_most_recently_modified_transcript(tmp_path):
    older = _make_transcript(tmp_path, "antigravity", "aaa")
    time.sleep(0.02)
    newer = _make_transcript(tmp_path, "antigravity-ide", "bbb")
    result = find_active_antigravity_transcript(tmp_path)
    assert result == newer
    assert result != older


def test_finds_transcripts_under_either_product_directory_name(tmp_path):
    """Both "antigravity" (older) and "antigravity-ide" (current) have been
    observed in the wild - the glob must not hardcode either."""
    path = _make_transcript(tmp_path, "antigravity-ide", "ccc")
    assert find_active_antigravity_transcript(tmp_path) == path


def test_ignores_non_transcript_files(tmp_path):
    brain_dir = tmp_path / "antigravity" / "brain" / "uuid1"
    brain_dir.mkdir(parents=True)
    (brain_dir / "task.md").write_text("not a transcript", encoding="utf-8")
    assert find_active_antigravity_transcript(tmp_path) is None


def test_claude_and_antigravity_discovery_are_independent(tmp_path):
    """Sanity check that the two discovery functions don't accidentally
    share state or a default root."""
    assert find_active_transcript(tmp_path / "nope") is None
    assert find_active_antigravity_transcript(tmp_path / "also_nope") is None
