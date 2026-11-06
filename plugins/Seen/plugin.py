"""Reuse Limnoria's Seen behavior while reading Unicode CSV records correctly."""

import csv
from pathlib import Path

from supybot import conf, plugins, world
from supybot.plugins.Seen.plugin import Seen as BundledSeen, SeenDB


class SafeSeenDB(SeenDB):
    """Read complete CSV records without splitting on Unicode line separators."""

    def __init__(self, filename):
        plugins.ChannelUserDictionary.__init__(self)
        self.filename = filename
        if not Path(filename).exists():
            return
        with open(filename, encoding="utf-8", newline="") as stream:
            for row in csv.reader(stream):
                if len(row) != 4:
                    raise ValueError("Seen CSV must contain exactly four fields per record")
                channel, nick, *value = row
                try:
                    nick = int(nick)
                except ValueError:
                    pass
                self[channel, nick] = self.deserialize(channel, nick, value)


class Seen(BundledSeen):
    """Keep bundled Seen commands and event handling with safe CSV storage."""

    def __init__(self, irc):
        # Bundled callbacks use the Seen private parent and these storage attributes.
        self._Seen__parent = super(BundledSeen, self)
        self._Seen__parent.__init__(irc)
        self.db = SafeSeenDB(conf.supybot.directories.data.dirize("Seen.db"))
        self.anydb = SafeSeenDB(conf.supybot.directories.data.dirize("Seen.any.db"))
        self.lastmsg = {}
        world.flushers.append(self.db.flush)
        world.flushers.append(self.anydb.flush)
