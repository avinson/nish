"""Build a private runtime config while retaining credentials and channel settings."""

import argparse
from pathlib import Path
import re

ENABLED = (
    "Admin Channel Config Misc Owner User Cobe Infobot Karma Seen ChannelLogger "
    "SpiffyTitles QuoteGrabs Later"
).split()

PLUGIN_DEFAULTS = {
    "timeout": "5",
    "cacheLifetime": "600",
    "channelWhitelist": "#nish",
    "snarfMultipleUrls": "False",
    "cooldownSeconds": "5",
    "badLinkText": "",
    "default.enabled": "True",
    "youtube.enabled": "True",
    "youtube.template": (
        "▶ {{title}}{% if duration %} | {{duration}}{% endif %}"
        "{% if view_count %} | {{view_count}} views{% endif %}"
        "{% if channel_title %} | {{channel_title}}{% endif %}"
        "{% if published %} | {{published}}{% endif %}"
    ),
    **{f"{handler}.enabled": "False" for handler in (
        "imdb", "wikipedia", "reddit", "imgur", "dailymotion", "twitch", "vimeo", "coub", "twitter"
    )},
}


def configure(source, output, root, repository, youtube_key_file=None, omdb_key_file=None):
    """Keep existing active settings and replace obsolete runtime selections."""
    values = {}
    key = None
    for line in source.read_text().splitlines():
        match = re.match(r"^(supybot\.[^:]+):\s*(.*)$", line)
        if match:
            key = match[1]
            values[key] = line
        elif key and line[:1].isspace() and not line.lstrip().startswith("#"):
            values[key] += "\n" + line
        else:
            key = None
    enabled = {name.lower() for name in ENABLED}
    for key in list(values):
        parts = key.split(".")
        if key.startswith("supybot.plugins.") and len(parts) >= 3:
            if parts[2].lower() not in enabled and parts[2] != "alwaysLoadImportant":
                del values[key]
        elif key.startswith("supybot.networks.") and len(parts) >= 3 and parts[2] != "Skub":
            del values[key]
    replacements = {
        "supybot.plugins": " ".join(ENABLED),
        "supybot.networks": "Skub",
        "supybot.networks.Skub.servers": "irc.darwin.network:6697",
        "supybot.networks.Skub.ssl": "True",
        "supybot.protocols.ssl.verifyCertificates": "True",
        "supybot.drivers.module": "Socket",
        "supybot.databases": "sqlite3 flat",
        "supybot.directories.plugins": str(repository / "plugins"),
        "supybot.log.level": "INFO",
        "supybot.log.stdout": "True",
        "supybot.log.stdout.level": "INFO",
        "supybot.pidFile": str(root / "nishbot.pid"),
        "supybot.plugins.ChannelLogger": "True",
        "supybot.plugins.ChannelLogger.rotateLogs": "True",
        "supybot.plugins.ChannelLogger.directories.timestamp": "False",
        "supybot.plugins.ChannelLogger.filenameTimestamp": "%Y-%m-%d",
        "supybot.plugins.ChannelLogger.flushImmediately": "True",
    }
    for name in ENABLED:
        replacements["supybot.plugins." + name] = "True"
    # Preserve operator overrides and private API keys on subsequent regeneration.
    for key, value in PLUGIN_DEFAULTS.items():
        key = "supybot.plugins.SpiffyTitles." + key
        values.setdefault(key, key + ": " + value)
    for key_file, name in (
        (youtube_key_file, "youtube.developerKey"), (omdb_key_file, "imdb.omdbAPI"),
    ):
        if key_file is None:
            continue
        secret = key_file.read_text().strip()
        if not secret or any(c.isspace() or ord(c) < 32 for c in secret):
            raise ValueError("API key files must contain a single nonempty token")
        key = "supybot.plugins.SpiffyTitles." + name
        values[key] = key + ": " + secret
        if name == "imdb.omdbAPI":
            key = "supybot.plugins.SpiffyTitles.imdb.enabled"
            values[key] = key + ": True"
    for name in ("conf", "data", "log", "backup"):
        replacements["supybot.directories." + name] = str(
            root / ("logs" if name == "log" else name)
        )
    replacements["supybot.directories.data.tmp"] = str(root / "data/tmp")
    for key, value in replacements.items():
        values[key] = key + ": " + value
    output.write_text("\n".join(values[k] for k in sorted(values)) + "\n")
    output.chmod(0o600)


def main():
    """Create a separate candidate config; never print credential values."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--root", type=Path, default=Path("/home/avinson/nishbot"))
    parser.add_argument("--repository", type=Path, default=Path("/home/avinson/git/avinson/nish"))
    parser.add_argument("--youtube-key-file", type=Path)
    parser.add_argument("--omdb-key-file", type=Path)
    args = parser.parse_args()
    configure(
        args.source, args.output, args.root, args.repository,
        args.youtube_key_file, args.omdb_key_file,
    )


if __name__ == "__main__":
    main()
