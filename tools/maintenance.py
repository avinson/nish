"""Bound bot maintenance to verified backups and closed history files."""

import argparse
from collections import defaultdict
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import time

BACKUP = re.compile(
    r"^(Infobot\.pickle\.db|users\.conf|channels\.conf|ignores\.conf|nishbot\.conf)\.backup\.(\d+)$"
)


def hash_file(stream, algorithm="sha256"):
    """Hash a stream without loading a database or backup into memory."""
    digest = hashlib.new(algorithm)
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest


def regular(path, device):
    """Accept regular files on the expected filesystem, excluding all symlinks."""
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and info.st_dev == device


def cleanup(root, receipts, apply=False):
    """Prune only old backup files with exact verified off-host hashes."""
    directory = root / "backup"
    if directory.is_symlink() or root.is_symlink():
        raise ValueError("Symlink root or backup directory")
    receipt = json.loads(receipts.read_text())["files"]
    groups = defaultdict(list)
    device = root.stat().st_dev
    for path in directory.iterdir():
        match = BACKUP.fullmatch(path.name)
        if match and regular(path, device):
            groups[match[1]].append((int(match[2]), path))
    selected = []
    for files in groups.values():
        for _, path in sorted(files, reverse=True)[10:]:
            expected = receipt.get(path.name)
            if not expected:
                continue
            with path.open("rb") as stream:
                actual = hash_file(stream).hexdigest()
            if actual != expected:
                continue
            selected.append({"name": path.name, "bytes": path.stat().st_size})
            if apply:
                path.unlink()
    return {"apply": apply, "files": len(selected), "bytes": sum(x["bytes"] for x in selected)}


def snapshot(root, destination):
    """Atomically replace one recovery copy after SQLite and hash verification."""
    if root.is_symlink() or destination.is_symlink():
        raise ValueError("Snapshot roots must not be symlinks")
    destination.mkdir(parents=True, mode=0o700, exist_ok=True)
    databases = [(p, p.relative_to(root)) for p in (root / "data").glob("*/cobe.brain")]
    databases += [(p, p.relative_to(root)) for p in (root / "data").glob("*/*.sqlite*.db")]
    quassel = Path("/home/avinson/services/quassel/data/quassel-storage.sqlite")
    if quassel.exists():
        databases.append((quassel, Path("quassel/quassel-storage.sqlite")))
    biggest = max(p.stat().st_size for p, _ in databases)
    if shutil.disk_usage(root).free < biggest + 1024**3:
        raise RuntimeError("Snapshot skipped: replacement size plus 1 GiB reserve is unavailable")
    manifest = {"created": time.time(), "files": {}}
    for source, relative in databases:
        target = destination / relative
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if target.is_symlink() or not regular(source, root.stat().st_dev):
            raise ValueError("Unsafe snapshot file")
        temp = target.with_name(target.name + ".next")
        if temp.exists():
            raise FileExistsError("Remove or inspect incomplete snapshot: " + str(temp))
        try:
            with source.open("rb") as stream:
                modern = stream.read(16) == b"SQLite format 3\x00"
            if modern:
                with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=15) as old:
                    with sqlite3.connect(temp) as new:
                        old.backup(new, pages=256, sleep=0.05)
                        if new.execute("PRAGMA quick_check").fetchone() != ("ok",):
                            raise ValueError("Snapshot failed SQLite integrity check")
            elif source.name == "Karma.sqlite.db":
                # This legacy plugin has not written since its SQLite 2 driver disappeared.
                shutil.copy2(source, temp)
                dump = subprocess.run(
                    ["/usr/bin/sqlite", str(source), ".dump"], check=True, capture_output=True
                ).stdout
                target.with_name(target.name + ".sql").write_bytes(dump)
                summary = (
                    subprocess.run(
                        [
                            "/usr/bin/sqlite",
                            str(source),
                            "SELECT count(*),sum(added),sum(subtracted) FROM karma;",
                        ],
                        check=True,
                        capture_output=True,
                    )
                    .stdout.decode()
                    .strip()
                )
                target.with_name(target.name + ".summary.json").write_text(json.dumps(summary))
            else:
                raise ValueError("Unrecognized database format: " + str(source))
            temp.chmod(0o600)
            with temp.open("rb") as stream:
                digest = hash_file(stream).hexdigest()
            os.replace(temp, target)
            manifest["files"][str(relative)] = digest
        finally:
            if temp.exists():
                temp.unlink()
    for dirname in ("conf",):
        shutil.copytree(root / dirname, destination / dirname, dirs_exist_ok=True)
    shutil.copy2(root / "nishbot.conf", destination / "nishbot.conf")
    for name in ("Seen.db", "Seen.any.db"):
        # Seen is atomically replaced by the bot; each copy is a complete old or new file.
        shutil.copy2(root / "data" / name, destination / "data" / name)
    for source in (root / "data").glob("*/Infobot.pickle.db"):
        target = destination / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(source, target)
    for path in destination.rglob("*"):
        if path.is_file() and path.name not in ("manifest.json", "manifest.next"):
            with path.open("rb") as stream:
                manifest["files"][str(path.relative_to(destination))] = hash_file(
                    stream
                ).hexdigest()
    manifest_path = destination / "manifest.json"
    manifest_path.with_suffix(".next").write_text(json.dumps(manifest, indent=2))
    os.replace(manifest_path.with_suffix(".next"), manifest_path)
    return {"snapshot_databases": len(databases), "destination": str(destination)}


def history(root, receipts, apply=False):
    """Compress closed channel logs; prune only exact archived compressed files."""
    directory = root / "logs" / "ChannelLogger"
    if not directory.exists():
        return {"compressed": 0, "pruned": 0}
    receipt = json.loads(receipts.read_text()).get("history", {}) if receipts.exists() else {}
    compressed = pruned = 0
    device = root.stat().st_dev
    for path in directory.rglob("*"):
        if path.is_symlink() or any(p.is_symlink() for p in path.parents) or not path.is_file():
            continue
        if not regular(path, device):
            continue
        age = time.time() - path.stat().st_mtime
        if path.suffix == ".log" and age > 2 * 86400:
            target = path.with_suffix(".log.gz")
            if not target.exists() and apply:
                with path.open("rb") as src, gzip.open(target, "xb") as dst:
                    shutil.copyfileobj(src, dst)
                shutil.copystat(path, target)
                with gzip.open(target, "rb") as check, path.open("rb") as original:
                    if hash_file(check).digest() != hash_file(original).digest():
                        raise ValueError("History compression verification failed")
                path.unlink()
            compressed += 1
        elif path.suffix == ".gz" and age > 90 * 86400:
            key = str(path.relative_to(root))
            with path.open("rb") as stream:
                digest = hash_file(stream).hexdigest()
            if receipt.get(key) == digest:
                if apply:
                    path.unlink()
                pruned += 1
    return {"compressed": compressed, "pruned": pruned}


def main():
    """Run locked maintenance; cleanup is a dry run unless --apply is present."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["cleanup", "snapshot", "disk", "health"])
    parser.add_argument("--root", type=Path, default=Path("/home/avinson/nishbot"))
    parser.add_argument(
        "--receipts",
        type=Path,
        default=Path("/home/avinson/nishbot-recovery/archive-receipts.json"),
    )
    parser.add_argument(
        "--destination", type=Path, default=Path("/home/avinson/nishbot-recovery/current")
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.root.absolute()
    with (root / ".maintenance.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "cleanup":
            result = cleanup(root, args.receipts, args.apply)
            result["history"] = history(root, args.receipts, args.apply)
        elif args.action == "snapshot":
            if not args.apply:
                raise SystemExit("Snapshot writes require --apply")
            result = snapshot(root, args.destination)
        else:
            usage = shutil.disk_usage(root)
            result = {
                "free_bytes": usage.free,
                "used_percent": round(100 * usage.used / usage.total, 1),
                "status": "low"
                if usage.free < 2 * 1024**3 or usage.free / usage.total < 0.1
                else "ok",
            }
            if args.action == "health":
                active = subprocess.run(
                    ["systemctl", "is-active", "nishbot"], capture_output=True, text=True
                )
                result["service"] = active.stdout.strip()
                pid = subprocess.check_output(
                    ["systemctl", "show", "nishbot", "-p", "MainPID", "--value"], text=True
                ).strip()
                logs = subprocess.run(
                    ["journalctl", "-u", "nishbot", "_PID=" + pid, "--since", "-1 hour", "--no-pager", "-o", "cat"],
                    capture_output=True, text=True, check=True,
                )
                result["recent_error_lines"] = sum(
                    line.startswith(("ERROR ", "CRITICAL ")) for line in logs.stdout.splitlines()
                )
                result["checked_at"] = time.time()
                if active.returncode or result.get("recent_error_lines"):
                    result["status"] = "attention"
                (root / "health.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        if result.get("status") in ("low", "attention"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
