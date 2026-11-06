"""Locate the bot's plugins without depending on an installed bot instance."""

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "plugins"))


def pytest_configure(config):
    """Give Limnoria's harness the same isolated directories as its own runner."""
    from supybot import conf, log, world

    config._nish_temp = tempfile.TemporaryDirectory(prefix="nishbot-tests-")
    for name in ("conf", "data", "log", "backup"):
        path = Path(config._nish_temp.name) / name
        path.mkdir()
        getattr(conf.supybot.directories, name).setValue(str(path))
    conf.supybot.directories.plugins.setValue([str(ROOT / "plugins")])
    conf.supybot.databases.setValue(["sqlite3", "flat"])
    conf.registerNetwork("test")
    conf.supybot.networks.test.servers.setValue(["localhost:6667"])
    conf.supybot.nick.setValue("test")
    conf.supybot.protocols.irc.throttleTime.setValue(0)
    conf.supybot.flush.setValue(False)
    world.testing = True
    world.myVerbose = 0
    log.testing = True
