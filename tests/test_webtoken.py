"""Pure-function coverage for the 'add to home screen' bearer-token path -
generation, hashing, verification, and disk persistence in isolation."""
from tether.miniapp import webtoken


def test_generate_produces_a_long_random_url_safe_string():
    a, b = webtoken.generate(), webtoken.generate()
    assert a != b
    assert len(a) > 32
    assert all(c.isalnum() or c in "-_" for c in a)


def test_hash_is_deterministic_and_not_the_raw_value():
    raw = "some-raw-token-value"
    h1, h2 = webtoken.hash_token(raw), webtoken.hash_token(raw)
    assert h1 == h2
    assert h1 != raw
    assert len(h1) == 64  # sha256 hex digest


def test_verify_accepts_matching_token_and_rejects_everything_else():
    raw = webtoken.generate()
    stored = webtoken.hash_token(raw)

    assert webtoken.verify(raw, stored) is True
    assert webtoken.verify("wrong-token", stored) is False
    assert webtoken.verify(raw, "wrong-hash") is False
    assert webtoken.verify(None, stored) is False
    assert webtoken.verify("", stored) is False
    assert webtoken.verify(raw, None) is False
    assert webtoken.verify(raw, "") is False


def test_issue_persists_only_the_hash_never_the_raw_token(monkeypatch, tmp_path):
    monkeypatch.setattr(webtoken, "STATE_DIR", tmp_path)
    monkeypatch.setattr(webtoken, "TOKEN_PATH", tmp_path / "web_token.json")

    raw = webtoken.issue()
    on_disk = (tmp_path / "web_token.json").read_text(encoding="utf-8")

    assert raw not in on_disk
    assert webtoken.hash_token(raw) in on_disk


def test_load_hash_round_trips_and_missing_file_is_none(monkeypatch, tmp_path):
    monkeypatch.setattr(webtoken, "STATE_DIR", tmp_path)
    monkeypatch.setattr(webtoken, "TOKEN_PATH", tmp_path / "web_token.json")

    assert webtoken.load_hash() is None

    raw = webtoken.issue()
    assert webtoken.load_hash() == webtoken.hash_token(raw)


def test_clear_removes_the_file_and_is_safe_to_call_twice(monkeypatch, tmp_path):
    monkeypatch.setattr(webtoken, "STATE_DIR", tmp_path)
    monkeypatch.setattr(webtoken, "TOKEN_PATH", tmp_path / "web_token.json")

    webtoken.issue()
    assert webtoken.load_hash() is not None

    webtoken.clear()
    assert webtoken.load_hash() is None
    webtoken.clear()  # missing_ok - must not raise
