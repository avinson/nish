"""Merge complete archived Seen records with newer records from a stopped bot."""

import argparse
import csv
import json
from pathlib import Path


def restore(root, baseline):
    """Keep the newest record per key; prefer the complete archive on timestamp ties."""
    report = {}
    for name in ("Seen.db", "Seen.any.db"):
        merged = {}
        for path in (baseline / name, root / "data" / name):
            with path.open(encoding="utf-8", newline="") as stream:
                for row in csv.reader(stream):
                    if len(row) != 4:
                        raise ValueError("Malformed Seen record")
                    channel, nick, timestamp, _ = row
                    try:
                        nick = int(nick)
                    except ValueError:
                        nick = nick.lower().translate(str.maketrans("[]\\^", "{}|~"))
                    key = (channel.lower(), nick)
                    if key not in merged or float(timestamp) > float(merged[key][2]):
                        merged[key] = row
        target = root / "data" / name
        temporary = target.with_name(target.name + ".next")
        if temporary.exists():
            raise FileExistsError(temporary)
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows(merged.values())
        temporary.chmod(0o600)
        temporary.replace(target)
        report[name] = {"records": len(merged)}
    return report


def main():
    """Repair only explicitly selected stopped-state files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("baseline", type=Path)
    args = parser.parse_args()
    print(json.dumps(restore(args.root, args.baseline)))


if __name__ == "__main__":
    main()
