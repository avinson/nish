"""Prove maintenance cannot remove active state or unarchived backups."""

import hashlib
import json
from pathlib import Path

import pytest

from tools.maintenance import cleanup


def test_backup_allowlist_and_receipts(tmp_path):
    backup = tmp_path / "backup"
    backup.mkdir()
    files = {}
    for i in range(15):
        name = f"Infobot.pickle.db.backup.{i}"
        content = str(i).encode()
        (backup / name).write_bytes(content)
        files[name] = hashlib.sha256(content).hexdigest()
    protected = [
        backup / "cobe.brain",
        backup / "unknown.backup.0",
        tmp_path / "quassel-storage.sqlite",
    ]
    for path in protected:
        path.write_text("keep")
    (backup / "users.conf.backup.0").symlink_to(protected[0])
    receipts = tmp_path / "receipt.json"
    receipts.write_text(json.dumps({"files": files}))
    assert cleanup(tmp_path, receipts)["files"] == 5
    assert len(list(backup.glob("Infobot*"))) == 15
    del files["Infobot.pickle.db.backup.0"]
    files["Infobot.pickle.db.backup.1"] = "wrong"
    receipts.write_text(json.dumps({"files": files}))
    assert cleanup(tmp_path, receipts, apply=True)["files"] == 3
    assert all(p.exists() for p in protected)
    assert (backup / "Infobot.pickle.db.backup.0").exists()
    assert (backup / "Infobot.pickle.db.backup.1").exists()
    assert (backup / "users.conf.backup.0").is_symlink()


def test_reject_symlink_backup_directory(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "backup").symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError):
        cleanup(tmp_path, Path("irrelevant"), apply=True)
