"""Check that modernization preserves private settings without retaining stale plugins."""

from tools.configure import ENABLED, PLUGIN_DEFAULTS, configure


def test_private_settings_and_allowlist(tmp_path):
    source = tmp_path / "old.conf"
    source.write_text(
        "supybot.networks.Skub.password: synthetic-test-value\n"
        "supybot.networks.Skub.channels: #one #two\n"
        "supybot.networks.Skub.channels.key.#two: synthetic-key\n"
        "supybot.networks.Freenode.ssl: False\n"
        "supybot.plugins.Titler: False\n"
        "supybot.plugins.I18nPlaceholder: True\n"
        "supybot.plugins.Infobot.personality: True\n"
        "supybot.plugins.Cobe.probability: 100\n"
        "supybot.plugins.Cobe.probability.#one: 500\n"
        "supybot.capabilities: -owner -admin -trusted\n"
    )
    target = tmp_path / "new.conf"
    configure(source, target, tmp_path / "runtime", tmp_path / "repo")
    text = target.read_text()
    assert "password: synthetic-test-value" in text
    assert "key.#two: synthetic-key" in text
    assert "channels: #one #two" in text
    assert "Freenode" not in text
    assert "supybot.plugins.Titler: False\n" in text
    assert "I18nPlaceholder" not in text
    assert "capabilities: -owner -admin -trusted" in text
    assert "supybot.protocols.ssl.verifyCertificates: True" in text
    assert "supybot.plugins.ChannelLogger.rotateLogs: True" in text
    assert "supybot.plugins.Cobe.probability: 200\n" in text
    assert "supybot.plugins.Cobe.probability.#one: 500\n" in text
    assert target.stat().st_mode & 0o777 == 0o600


def test_new_plugins_and_overrides_survive_regeneration(tmp_path):
    source = tmp_path / "source.conf"
    source.write_text(
        "supybot.plugins.SpiffyTitles.youtube.developerKey: synthetic-youtube-key\n"
        "supybot.plugins.SpiffyTitles.imdb.omdbAPI: synthetic-omdb-key\n"
        "supybot.plugins.SpiffyTitles.imdb.enabled: True\n"
        "supybot.plugins.SpiffyTitles.channelWhitelist: #darwin,#nish\n"
        "supybot.plugins.QuoteGrabs.randomGrabber: False\n"
        "supybot.plugins.Later.private: False\n"
    )
    target = tmp_path / "target.conf"
    configure(source, target, tmp_path / "runtime", tmp_path / "repo")
    text = target.read_text()
    for line in source.read_text().splitlines():
        assert line in text
    for plugin in ("QuoteGrabs", "Later"):
        assert plugin in ENABLED
        assert f"supybot.plugins.{plugin}: True\n" in text
    assert "SpiffyTitles" not in ENABLED
    assert "supybot.plugins.SpiffyTitles: False\n" in text
    configure(target, source, tmp_path / "runtime", tmp_path / "repo")
    assert source.read_text() == text


def test_preview_defaults_match_template(tmp_path):
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "nishbot.conf.tmpl"
    template = source.read_text()
    target = tmp_path / "target.conf"
    configure(source, target, tmp_path / "runtime", tmp_path / "repo")
    for key, value in PLUGIN_DEFAULTS.items():
        expected = f"supybot.plugins.SpiffyTitles.{key}: {value}".rstrip()
        assert expected in template
        assert expected in target.read_text()


def test_private_key_file_provisioning(tmp_path):
    source = tmp_path / "source.conf"
    source.write_text("")
    key = tmp_path / "key"
    key.write_text("synthetic-private-key\n")
    target = tmp_path / "target.conf"
    configure(source, target, tmp_path, tmp_path, key, key)
    text = target.read_text()
    assert "youtube.developerKey: synthetic-private-key" in text
    assert "imdb.omdbAPI: synthetic-private-key" in text
    assert "imdb.enabled: True" in text
    assert target.stat().st_mode & 0o777 == 0o600
    key.write_text("invalid\nsecond line")
    import pytest

    with pytest.raises(ValueError, match="single nonempty token"):
        configure(source, target, tmp_path, tmp_path, key)
