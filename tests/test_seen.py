"""Preserve historical Seen records containing Unicode line separators."""

import csv

from Seen.plugin import SafeSeenDB


def test_unicode_line_separator_round_trip(tmp_path):
    path = tmp_path / "Seen.db"
    records = [
        ["#darwin", "someone", "1234.0", "a message\u2028with two parts"],
        ["#darwin", "another", "1235.0", "café 🙂"],
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(records)
    db = SafeSeenDB(str(path))
    assert len(list(db.items())) == 2
    assert db.seen("#darwin", "someone")[1] == records[0][3]
    db.flush()
    reopened = SafeSeenDB(str(path))
    assert len(list(reopened.items())) == 2
    assert reopened.seen("#darwin", "someone")[1] == records[0][3]
