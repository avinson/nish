"""Build and evaluate a separate corpus without changing the deployed brain."""

import argparse
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import tarfile
import time
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/Cobe"))
from core import clean_input

ZONE = ZoneInfo("America/Los_Angeles")
CHAT = re.compile(r"^(\d\d:\d\d) <[ @+]*([^ >]+)> (.*)$")
BOT = re.compile(r"^nish[_\x60]*$", re.IGNORECASE)
RAW = re.compile(
    r"^DEBUG (\d{4}-\d\d-\d\d)T(\d\d:\d\d):\d\d .*Incoming message \(Skub\): :([^! ]+)![^ ]+ PRIVMSG (#darwin) :(.*)$"
)


def export(destination):
    """Merge only #darwin sources and deduplicate overlapping log observations."""
    work = destination / "evaluation"
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    database = work / "corpus.sqlite3"
    if database.exists():
        raise FileExistsError("Move the previous evaluation before exporting again")
    db = sqlite3.connect(database)
    db.execute(
        "CREATE TABLE messages (id TEXT PRIMARY KEY, minute TEXT, nick TEXT, text TEXT, source TEXT)"
    )
    counts = {}

    def add(minute, nick, text, source):
        if BOT.fullmatch(nick) or re.match(r"^[.@!$%]", text):
            return
        key = hashlib.sha256(
            json.dumps([minute, nick.lower(), text], ensure_ascii=True).encode()
        ).hexdigest()
        result = db.execute(
            "INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?)", (key, minute, nick, text, source)
        )
        counts[source] = counts.get(source, 0) + result.rowcount

    archives = sorted(destination.glob("*/config-source-history-backups.tar.gz"))
    for archive in archives:
        with tarfile.open(archive, "r|gz") as tar:
            for member in tar:
                match = re.search(r"irclogs/(\d{4})/skub/#darwin\.(\d\d)-(\d\d)\.log$", member.name)
                if not match or not member.isfile():
                    continue
                day = "-".join(match.groups())
                for line in tar.extractfile(member).read().decode("utf-8").splitlines():
                    m = CHAT.match(line.rstrip("\n"))
                    if m:
                        add(day + "T" + m[1], m[2], m[3], "irssi")
    quassel = destination / "current/quassel/quassel-storage.sqlite"
    if quassel.exists():
        with sqlite3.connect(quassel.as_uri() + "?mode=ro", uri=True) as source:
            for epoch, sender, text in source.execute(
                "SELECT backlog.time,sender.sender,message FROM backlog JOIN sender USING(senderid) JOIN buffer USING(bufferid) WHERE lower(buffername)='#darwin' AND backlog.type=1 ORDER BY messageid"
            ):
                minute = datetime.datetime.fromtimestamp(epoch / 1000, ZONE).strftime(
                    "%Y-%m-%dT%H:%M"
                )
                add(minute, sender.split("!", 1)[0], text, "quassel")
    for path in destination.glob("*/bot-log-pre-upgrade.gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="strict") as stream:
            for line in stream:
                m = RAW.match(line.rstrip("\n"))
                if m:
                    add(m[1] + "T" + m[2], m[3], m[5], "bot_log")
    db.commit()
    users = [row[0] for row in db.execute("SELECT DISTINCT nick FROM messages")]
    written = 0
    corpus = work / "darwin.txt"
    with corpus.open("w", encoding="utf-8") as stream:
        for (text,) in db.execute("SELECT text FROM messages ORDER BY minute,id"):
            text = clean_input(text, users)
            if text and len(text.split()) >= 3:
                stream.write(text + "\n")
                written += 1
    report = {
        "unique_source_messages": counts,
        "training_lines": written,
        "coverage": db.execute("SELECT min(minute),max(minute) FROM messages").fetchone(),
        "uncovered_period": "March 2018 to July 2023; possible earlier and imported training",
        "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
    }
    (work / "corpus-report.json").write_text(json.dumps(report, indent=2))
    db.close()
    print(json.dumps(report))


def evaluate(destination):
    """Measure Markovify on the clean corpus; keep generated text private."""
    import markovify

    work = destination / "evaluation"
    started = time.monotonic()
    with (work / "darwin.txt").open(encoding="utf-8") as stream:
        model = markovify.NewlineText(
            stream, state_size=3, retain_original=False, well_formed=False
        )
    build = time.monotonic() - started
    samples = []
    durations = []
    for _ in range(100):
        start = time.monotonic()
        text = model.make_short_sentence(300, tries=25)
        durations.append(time.monotonic() - start)
        if text:
            samples.append(text)
    (work / "markovify-samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2))
    (work / "markovify-model.json").write_text(model.to_json())
    report = {
        "engine": "markovify 0.9.4",
        "state_size": 3,
        "build_seconds": round(build, 3),
        "successful_samples": len(samples),
        "sample_attempts": 100,
        "generation_p95_seconds": round(sorted(durations)[94], 4),
        "deployed": False,
        "limitation": "This corpus cannot reproduce the uncovered training history.",
    }
    (work / "markovify-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


def main():
    """Run an explicit offline export or evaluation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "evaluate"])
    parser.add_argument("--archive", type=Path, default=Path.home() / "nishbot-archive/drebin")
    args = parser.parse_args()
    (export if args.action == "export" else evaluate)(args.archive)


if __name__ == "__main__":
    main()
