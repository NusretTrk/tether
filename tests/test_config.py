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
