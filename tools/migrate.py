"""Convert a trusted legacy state copy without executing pickle globals."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import pickle
import sqlite3
import subprocess


class LegacyDict(dict):
    """Represent only the old InsensitivePreservingDict pickle constructor."""


class RestrictedUnpickler(pickle.Unpickler):
    """Reject every global except the known legacy dictionary type."""

    def find_class(self, module, name):
        """Map the legacy type to a plain dictionary without importing code."""
        if (module, name) == ("supybot.utils.gen", "InsensitivePreservingDict"):
            return LegacyDict
        raise pickle.UnpicklingError("Unexpected pickle global: " + module + "." + name)


def decode(value, encodings):
    """Decode legacy bytes with a lossless, counted encoding choice."""
    if isinstance(value, str):
        return value
    if not isinstance(value, bytes):
        raise TypeError("Fact keys and values must be text")
    for encoding in ("utf-8", "cp1252", "latin1"):
        try:
            text = value.decode(encoding)
            assert text.encode(encoding) == value
            encodings[encoding] = encodings.get(encoding, 0) + 1
            return text
        except UnicodeDecodeError:
            pass
    raise AssertionError("Unreachable decoding failure")


def migrate_infobot(source, target):
    """Convert both dictionaries, then verify all records and database integrity."""
    if target.exists():
        raise FileExistsError(target)
    with source.open("rb") as stream:
        facts = RestrictedUnpickler(stream, encoding="bytes").load()
        if stream.read():
            raise ValueError("Trailing pickle data")
    if not isinstance(facts, tuple) or len(facts) != 2:
        raise ValueError("Unexpected Infobot container")
    encodings = {}
    counts = {}
    digest = hashlib.sha256()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(target) as db:
        for table, dictionary in zip(("isFacts", "areFacts"), facts, strict=True):
            if not isinstance(dictionary, LegacyDict):
                raise ValueError("Unexpected fact dictionary")
            db.execute(
                f"CREATE TABLE {table} (normalized TEXT PRIMARY KEY, "
                "key TEXT NOT NULL, value TEXT NOT NULL)"
            )
            records = [(decode(k, encodings), decode(v, encodings)) for k, v in dictionary.items()]
            db.executemany(
                f"INSERT INTO {table} VALUES (?,?,?)", [(k.lower(), k, v) for k, v in records]
            )
            actual = db.execute(f"SELECT key,value FROM {table} ORDER BY key").fetchall()
            assert actual == sorted(records)
            digest.update(json.dumps(actual, ensure_ascii=True).encode())
            counts[table] = len(records)
        db.commit()
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    os.chmod(target, 0o600)
    return {"counts": counts, "encodings": encodings, "records_sha256": digest.hexdigest()}


def migrate_state(root):
    """Migrate only a stopped or isolated state directory."""
    report = {}
    for source in sorted((root / "data").glob("*/Infobot.pickle.db")):
        report[source.parent.name] = migrate_infobot(source, source.with_name("Infobot.sqlite3.db"))
    for name in ("Seen.db", "Seen.any.db"):
        path = root / "data" / name
        encodings = {}
        raw = path.read_bytes()
        text = decode(raw, encodings)
        # Limnoria retains the CSV storage format. Preserve all records and timestamps.
        path.write_text(text, encoding="utf-8", newline="")
        report[name] = {
            "bytes_before": len(raw),
            "encodings": encodings,
            "lines": len(text.splitlines()),
        }
    for path in (root / "data").glob("*/Karma.sqlite.db"):
        target = path.with_name("Karma.sqlite3.db")
        if target.exists():
            raise FileExistsError(target)
        with path.open("rb") as stream:
            modern = stream.read(16) == b"SQLite format 3\x00"
        with sqlite3.connect(target) as new:
            if modern:
                with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as old:
                    old.backup(new)
                    assert (
                        old.execute("SELECT * FROM karma ORDER BY id").fetchall()
                        == new.execute("SELECT * FROM karma ORDER BY id").fetchall()
                    )
            else:
                dump_path = path.with_name(path.name + ".sql")
                summary_path = path.with_name(path.name + ".summary.json")
                if dump_path.exists() and summary_path.exists():
                    dump = dump_path.read_bytes()
                    summary = json.loads(summary_path.read_text())
                else:
                    dump = subprocess.run(
                        ["/usr/bin/sqlite", str(path), ".dump"], check=True, capture_output=True
                    ).stdout
                    summary = (
                        subprocess.run(
                            [
                                "/usr/bin/sqlite",
                                str(path),
                                "SELECT count(*),sum(added),sum(subtracted) FROM karma;",
                            ],
                            check=True,
                            capture_output=True,
                        )
                        .stdout.decode()
                        .strip()
                    )
                new.executescript(decode(dump, {}))
                actual = new.execute(
                    "SELECT count(*),sum(added),sum(subtracted) FROM karma"
                ).fetchone()
                assert "|".join(str(v) if v is not None else "" for v in actual) == summary
                with sqlite3.connect(":memory:") as expected:
                    expected.executescript(decode(dump, {}))
                    assert (
                        expected.execute("SELECT * FROM karma ORDER BY id").fetchall()
                        == new.execute("SELECT * FROM karma ORDER BY id").fetchall()
                    )
            assert new.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            report[str(path.relative_to(root))] = {
                "records": new.execute("SELECT count(*) FROM karma").fetchone()[0],
                "source_format": "SQLite3" if modern else "SQLite2",
            }
    return report


def main():
    """Write a migration report containing counts and hashes, never fact text."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(migrate_state(args.root.resolve()), indent=2))


if __name__ == "__main__":
    main()
