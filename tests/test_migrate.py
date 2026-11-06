"""Check strict migration boundaries and value preservation."""

import io
import pickle
import sqlite3
import sys
import types

import pytest

from tools.migrate import LegacyDict, RestrictedUnpickler, migrate_infobot


def test_disallow_pickle_code():
    with pytest.raises(pickle.UnpicklingError):
        RestrictedUnpickler(io.BytesIO(b"cos\nsystem\n(S'touch /tmp/never-nishbot'\ntR.")).load()


def test_fact_migration(tmp_path, monkeypatch):
    module = types.ModuleType("supybot.utils.gen")
    legacy = type("InsensitivePreservingDict", (dict,), {"__module__": "supybot.utils.gen"})
    module.InsensitivePreservingDict = legacy
    monkeypatch.setitem(sys.modules, "supybot.utils.gen", module)
    source = tmp_path / "Infobot.pickle.db"
    source.write_bytes(
        pickle.dumps((legacy({"Mixed CASE": "café 🙂"}), legacy({"things": "fine"})), protocol=2)
    )
    target = tmp_path / "Infobot.sqlite3.db"
    report = migrate_infobot(source, target)
    assert report["counts"] == {"isFacts": 1, "areFacts": 1}
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT * FROM isFacts").fetchone() == (
            "mixed case",
            "Mixed CASE",
            "café 🙂",
        )
    with pytest.raises(FileExistsError):
        migrate_infobot(source, target)


def test_legacy_dict_constructor():
    assert LegacyDict({b"key": b"value"})[b"key"] == b"value"
