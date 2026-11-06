"""SQLite storage for Infobot, with the original case-insensitive key behavior."""

import fnmatch
import os
import random
import sqlite3

from supybot import dbi, plugins


def create_schema(db):
    """Create the two fact tables without replacing any existing records."""
    for table in ("isFacts", "areFacts"):
        db.execute(
            f"CREATE TABLE IF NOT EXISTS {table} "
            "(normalized TEXT PRIMARY KEY, key TEXT NOT NULL, value TEXT NOT NULL)"
        )
    db.commit()


class InfobotDB:
    """Keep separate durable fact databases for each channel."""

    def __init__(self):
        self.dbs = {}
        self.changes = {}
        self.responses = {}

    def _getDb(self, channel):
        filename = plugins.makeChannelFilename("Infobot.sqlite3.db", channel)
        if filename not in self.dbs:
            existed = os.path.exists(filename)
            db = sqlite3.connect(filename)
            db.execute("PRAGMA synchronous=FULL")
            create_schema(db)
            self.dbs[filename] = db
            self.changes[filename] = self.responses[filename] = 0
            if not existed:
                from .plugin import initialIs, initialAre

                for table, initial in (("isFacts", initialIs), ("areFacts", initialAre)):
                    db.executemany(
                        f"INSERT INTO {table} VALUES (?,?,?)",
                        [(k.lower(), k, v) for k, v in initial.items()],
                    )
                db.commit()
        return self.dbs[filename], filename

    def close(self):
        """Close every database and allow later use after plugin reset."""
        for db in self.dbs.values():
            db.close()
        self.dbs.clear()

    def _get(self, channel, table, key):
        db, filename = self._getDb(channel)
        row = db.execute(f"SELECT value FROM {table} WHERE normalized=?", (key.lower(),)).fetchone()
        if row is None:
            raise dbi.NoRecordError(key)
        self.responses[filename] += 1
        return row[0]

    def _has(self, channel, table, key):
        db, _ = self._getDb(channel)
        return (
            db.execute(f"SELECT 1 FROM {table} WHERE normalized=?", (key.lower(),)).fetchone()
            is not None
        )

    def _set(self, channel, table, key, value):
        db, filename = self._getDb(channel)
        db.execute(
            f"INSERT INTO {table} VALUES (?,?,?) ON CONFLICT(normalized) "
            "DO UPDATE SET key=excluded.key,value=excluded.value",
            (key.lower(), key, value),
        )
        db.commit()
        self.changes[filename] += 1

    def _delete(self, channel, table, key):
        db, filename = self._getDb(channel)
        result = db.execute(f"DELETE FROM {table} WHERE normalized=?", (key.lower(),))
        if not result.rowcount:
            raise dbi.NoRecordError(key)
        db.commit()
        self.changes[filename] += 1

    def getIs(self, channel, key):
        """Get an is fact."""
        return self._get(channel, "isFacts", key)

    def getAre(self, channel, key):
        """Get an are fact."""
        return self._get(channel, "areFacts", key)

    def hasIs(self, channel, key):
        """Check an is fact."""
        return self._has(channel, "isFacts", key)

    def hasAre(self, channel, key):
        """Check an are fact."""
        return self._has(channel, "areFacts", key)

    def setIs(self, channel, key, value):
        """Set an is fact."""
        self._set(channel, "isFacts", key, value)

    def setAre(self, channel, key, value):
        """Set an are fact."""
        self._set(channel, "areFacts", key, value)

    def delIs(self, channel, key):
        """Delete an is fact."""
        self._delete(channel, "isFacts", key)

    def delAre(self, channel, key):
        """Delete an are fact."""
        self._delete(channel, "areFacts", key)

    def changeIs(self, channel, key, replacer):
        """Apply an edit to an is fact."""
        self.setIs(channel, key, replacer(self.getIs(channel, key)))

    def changeAre(self, channel, key, replacer):
        """Apply an edit to an are fact."""
        self.setAre(channel, key, replacer(self.getAre(channel, key)))

    def getDunno(self):
        """Select the original unknown-fact response."""
        from .plugin import dunnos, ends

        return random.choice(dunnos) + random.choice(ends)

    def getConfirm(self):
        """Select the original confirmation response."""
        from .plugin import confirms, ends

        return random.choice(confirms) + random.choice(ends)

    def getChangeCount(self, channel):
        """Count changes since this process opened the channel database."""
        _, filename = self._getDb(channel)
        return self.changes[filename]

    def getResponseCount(self, channel):
        """Count lookups since this process opened the channel database."""
        _, filename = self._getDb(channel)
        return self.responses[filename]

    def getNumFacts(self, channel):
        """Count all facts in the channel."""
        db, _ = self._getDb(channel)
        return sum(
            db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("isFacts", "areFacts")
        )

    def getFacts(self, channel, glob):
        """List fact keys matching a shell pattern."""
        db, _ = self._getDb(channel)
        return {
            k
            for table in ("isFacts", "areFacts")
            for (k,) in db.execute(f"SELECT key FROM {table}")
            if fnmatch.fnmatchcase(k.lower(), glob.lower())
        }
