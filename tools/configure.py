"""Build a private runtime config while retaining credentials and channel settings."""

import argparse
from pathlib import Path
import re

ENABLED = "Admin Channel Config Misc Owner User Cobe Infobot Karma Seen ChannelLogger".split()


def configure(source, output, root, repository):
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
    args = parser.parse_args()
    configure(args.source, args.output, args.root, args.repository)


if __name__ == "__main__":
    main()
