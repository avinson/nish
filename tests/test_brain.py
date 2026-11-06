"""Exercise unmodified cobe and its dependency overrides on real SQLite."""

import sqlite3

from cobe.brain import Brain

from Cobe.core import clean_input, clean_output


def test_durable_unicode_learning_and_reload(tmp_path):
    path = tmp_path / "cobe.brain"
    brain = Brain(str(path))
    brain.graph.commit()
    brain.graph.cursor().execute("PRAGMA synchronous=FULL")
    assert brain.graph.cursor().execute("PRAGMA synchronous").fetchone()[0] == 2
    for text in ("This café has good coffee", "The café has warm bread", "Warm bread tastes good"):
        brain.learn(text)
    before = brain.graph.cursor().execute("SELECT count(*) FROM tokens").fetchone()[0]
    result = clean_output(brain.reply("café coffee", loop_ms=20))
    assert result
    assert brain.graph.cursor().execute("SELECT count(*) FROM tokens").fetchone()[0] == before
    assert not clean_input("MAGIC_NICKnewword")
    brain.graph.close()
    reopened = Brain(str(path))
    assert reopened.reply("bread", loop_ms=20)
    reopened.graph.close()
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT text FROM info WHERE attribute='version'").fetchone()[0] == "2"
