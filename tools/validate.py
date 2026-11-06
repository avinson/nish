"""Check copied production brains without printing conversation text."""

import argparse
import json
from pathlib import Path
import resource
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/Cobe"))
from cobe.brain import Brain
from core import MARKERS, clean_output


def main():
    """Report integrity, generation latency, contamination filtering, and memory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    report = {}
    for path in sorted((args.root / "data").glob("*/cobe.brain")):
        with sqlite3.connect(path) as db:
            assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            tokens = db.execute("SELECT count(*) FROM tokens").fetchone()[0]
        brain = Brain(str(path))
        durations = []
        marked = 0
        for prompt in (
            "hello there",
            "according to everyone",
            "coffee bread",
            "computer code",
            "🙂 café",
        ):
            start = time.monotonic()
            reply = brain.reply(prompt, loop_ms=100, max_len=300)
            durations.append(time.monotonic() - start)
            marked += bool(MARKERS.search(reply))
            result = clean_output(reply)
            assert not MARKERS.search(result)
            assert len(result.encode()) <= 400
        brain.graph.close()
        report[path.parent.name] = {
            "tokens": tokens,
            "samples": len(durations),
            "raw_marker_samples": marked,
            "maximum_reply_seconds": round(max(durations), 3),
        }
    report["max_rss_kib_linux"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
