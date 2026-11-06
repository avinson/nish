"""Check that modernization preserves private settings without retaining stale plugins."""

from tools.configure import configure


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
        "supybot.capabilities: -owner -admin -trusted\n"
    )
    target = tmp_path / "new.conf"
    configure(source, target, tmp_path / "runtime", tmp_path / "repo")
    text = target.read_text()
    assert "password: synthetic-test-value" in text
    assert "key.#two: synthetic-key" in text
    assert "channels: #one #two" in text
    assert "Freenode" not in text
    assert "Titler" not in text
    assert "I18nPlaceholder" not in text
    assert "capabilities: -owner -admin -trusted" in text
    assert "supybot.protocols.ssl.verifyCertificates: True" in text
    assert "supybot.plugins.ChannelLogger.rotateLogs: True" in text
    assert target.stat().st_mode & 0o777 == 0o600
