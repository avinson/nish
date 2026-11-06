"""Check the deployed logger reopens a rotated file without a bot restart."""

import logging

from supybot.log import BetterFileHandler


def test_watched_log_reopens_after_rotation(tmp_path):
    path = tmp_path / "messages.log"
    handler = BetterFileHandler(path, encoding="utf-8")
    try:
        handler.emit(logging.makeLogRecord({"msg": "before rotation 🙂"}))
        rotated = tmp_path / "messages.log.1"
        path.rename(rotated)
        handler.emit(logging.makeLogRecord({"msg": "after rotation café"}))
        assert rotated.read_text() == "before rotation 🙂\n"
        assert path.read_text() == "after rotation café\n"
    finally:
        handler.close()
