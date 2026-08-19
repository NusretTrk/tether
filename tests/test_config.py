"""Config validation/fallback tests. Invalid values in config.yaml should
fall back to the default for that field with a warning, not crash — the
file is hand-edited and occasionally gets a typo."""
from tether.config import Settings


def test_defaults_are_valid():
    assert Settings().validate() == []


def test_invalid_language_falls_back(tmp_path, monkeypatch):
    import tether.config as config_mod
    path = tmp_path / "config.yaml"
    path.write_text("language: not-a-real-language\noutput_mode: summary\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", path)
    monkeypatch.setattr(config_mod, "CONFIG_EXAMPLE_PATH", path)

    settings = config_mod.Settings.load()
    assert settings.language == Settings().language  # fell back to default
    assert settings.output_mode == "summary"  # valid field kept as-is


def test_unknown_keys_ignored_not_fatal(tmp_path, monkeypatch):
    import tether.config as config_mod
    path = tmp_path / "config.yaml"
    path.write_text("language: en\nthis_key_does_not_exist: 123\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", path)
    monkeypatch.setattr(config_mod, "CONFIG_EXAMPLE_PATH", path)

    settings = config_mod.Settings.load()
    assert settings.language == "en"


def test_malformed_yaml_falls_back_to_full_defaults(tmp_path, monkeypatch):
    import tether.config as config_mod
    path = tmp_path / "config.yaml"
    path.write_text("language: [this is not: valid yaml structure\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", path)
    monkeypatch.setattr(config_mod, "CONFIG_EXAMPLE_PATH", path)

    settings = config_mod.Settings.load()
    assert settings == Settings()


def test_missing_config_file_uses_defaults(tmp_path, monkeypatch):
    import tether.config as config_mod
    missing = tmp_path / "does_not_exist.yaml"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", missing)
    monkeypatch.setattr(config_mod, "CONFIG_EXAMPLE_PATH", missing)

    settings = config_mod.Settings.load()
    assert settings == Settings()


def test_round_trip_save_and_load(tmp_path, monkeypatch):
    import tether.config as config_mod
    path = tmp_path / "config.yaml"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", path)
    monkeypatch.setattr(config_mod, "CONFIG_EXAMPLE_PATH", path)

    s = Settings()
    s.language = "tr"
    s.temp_emergency_c = 85
    s.save()

    loaded = config_mod.Settings.load()
    assert loaded.language == "tr"
    assert loaded.temp_emergency_c == 85


# ---- set_env_var: the one place a secret gets written from inside a
# running bot session (see transport/ngrok_setup.py) rather than a manual
# file edit, so it needs the same "never lose the rest of the file"
# rigor as the settings round-trip above, plus atomicity. ----

def test_set_env_var_appends_when_file_is_missing(tmp_path, monkeypatch):
    import tether.config as config_mod
    path = tmp_path / ".env"
    monkeypatch.setattr(config_mod, "ENV_PATH", path)

    config_mod.set_env_var("NGROK_AUTHTOKEN", "abc123")

    assert path.read_text(encoding="utf-8") == "NGROK_AUTHTOKEN=abc123\n"


def test_set_env_var_appends_new_key_preserving_existing_lines(tmp_path, monkeypatch):
    import tether.config as config_mod
    path = tmp_path / ".env"
    path.write_text("BOT_TOKEN=real-token\nCHAT_ID=123\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "ENV_PATH", path)

    config_mod.set_env_var("NGROK_AUTHTOKEN", "abc123")

    content = path.read_text(encoding="utf-8")
    assert "BOT_TOKEN=real-token" in content
    assert "CHAT_ID=123" in content
    assert "NGROK_AUTHTOKEN=abc123" in content


def test_set_env_var_replaces_existing_value_in_place(tmp_path, monkeypatch):
    import tether.config as config_mod
    path = tmp_path / ".env"
    path.write_text("BOT_TOKEN=real-token\nNGROK_AUTHTOKEN=old-value\nCHAT_ID=123\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "ENV_PATH", path)

    config_mod.set_env_var("NGROK_AUTHTOKEN", "new-value")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == ["BOT_TOKEN=real-token", "NGROK_AUTHTOKEN=new-value", "CHAT_ID=123"]


def test_set_env_var_does_not_touch_a_commented_out_line(tmp_path, monkeypatch):
    """A commented template line (# NGROK_AUTHTOKEN=, as shipped in
    .env.example) must not be mistaken for a live value - the real value
    should be appended fresh, not uncommented in place, since a line
    starting with '#' is a different line entirely as far as startswith
    is concerned."""
    import tether.config as config_mod
    path = tmp_path / ".env"
    path.write_text("BOT_TOKEN=real-token\n# NGROK_AUTHTOKEN=\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "ENV_PATH", path)

    config_mod.set_env_var("NGROK_AUTHTOKEN", "real-value")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert "# NGROK_AUTHTOKEN=" in lines
    assert "NGROK_AUTHTOKEN=real-value" in lines


def test_set_env_var_returns_true_when_verified_on_disk(tmp_path, monkeypatch):
    import tether.config as config_mod
    path = tmp_path / ".env"
    monkeypatch.setattr(config_mod, "ENV_PATH", path)

    assert config_mod.set_env_var("NGROK_AUTHTOKEN", "abc123") is True


def test_set_env_var_verification_survives_an_update_not_just_first_set(tmp_path, monkeypatch):
    """Regression guard: verification reads the file directly, not
    through os.environ - load_dotenv's default (never override an
    already-set variable) would make a naive os.environ-based check
    report success on the FIRST set but silently see the stale value on
    an UPDATE, since the env var is already populated by then."""
    import os
    import tether.config as config_mod
    path = tmp_path / ".env"
    monkeypatch.setattr(config_mod, "ENV_PATH", path)

    config_mod.set_env_var("NGROK_AUTHTOKEN", "first-value")
    os.environ["NGROK_AUTHTOKEN"] = "first-value"  # simulate load_dotenv having cached it once

    assert config_mod.set_env_var("NGROK_AUTHTOKEN", "second-value") is True
    assert config_mod.get_env_var("NGROK_AUTHTOKEN") == "second-value"
    del os.environ["NGROK_AUTHTOKEN"]


def test_get_env_var_returns_none_when_key_absent(tmp_path, monkeypatch):
    import tether.config as config_mod
    path = tmp_path / ".env"
    path.write_text("BOT_TOKEN=x\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "ENV_PATH", path)

    assert config_mod.get_env_var("NGROK_AUTHTOKEN") is None


def test_set_env_var_leaves_file_intact_if_write_is_interrupted(tmp_path, monkeypatch):
    """Simulates a crash mid-write: the atomic tmp-file-then-rename
    approach means the original .env must still be fully readable
    afterward, never truncated or half-written."""
    import tether.config as config_mod
    path = tmp_path / ".env"
    original = "BOT_TOKEN=real-token\nCHAT_ID=123\n"
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(config_mod, "ENV_PATH", path)

    from pathlib import Path
    real_replace = Path.replace

    def failing_replace(self, target):
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(Path, "replace", failing_replace)
    try:
        config_mod.set_env_var("NGROK_AUTHTOKEN", "x")
    except OSError:
        pass

    assert path.read_text(encoding="utf-8") == original  # untouched
