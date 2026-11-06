"""Pull protected recovery data to this Mac and acknowledge verified history."""

import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HOST = "avinson@drebin"
REMOTE = "/home/avinson/nishbot-recovery/current/"


def digest(path):
    """Hash a file without holding its contents in memory."""
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            result.update(block)
    return result.hexdigest()


def main():
    """Keep a current snapshot and acknowledge only locally verified log files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path.home() / "nishbot-archive/drebin")
    args = parser.parse_args()
    destination = args.destination
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.umask(0o077)
    with (destination / ".sync.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        incoming = destination / "incoming"
        incoming.mkdir(mode=0o700, exist_ok=True)
        subprocess.run(
            [
                "rsync",
                "-a",
                "--delete",
                "-e",
                "ssh -o BatchMode=yes -o ConnectTimeout=15",
                HOST + ":" + REMOTE,
                str(incoming) + "/",
            ],
            check=True,
        )
        manifest = json.loads((incoming / "manifest.json").read_text())
        for relative, expected in manifest["files"].items():
            path = incoming / relative
            if path.is_symlink() or not path.resolve().is_relative_to(incoming.resolve()):
                raise ValueError("Unsafe archive manifest path")
            if digest(path) != expected:
                raise ValueError("Snapshot changed or transfer failed: " + relative)
        current = destination / "current"
        previous = destination / "previous"
        if previous.exists():
            shutil.rmtree(previous)
        if current.exists():
            current.rename(previous)
        incoming.rename(current)
        history = destination / "history"
        history.mkdir(mode=0o700, exist_ok=True)
        exists = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", HOST, "test -d /home/avinson/nishbot/logs/ChannelLogger"]
        )
        if exists.returncode == 0:
            subprocess.run(
                [
                    "rsync",
                    "-a",
                    "-e",
                    "ssh -o BatchMode=yes -o ConnectTimeout=15",
                    "--include=*/",
                    "--include=*.gz",
                    "--exclude=*",
                    HOST + ":/home/avinson/nishbot/logs/ChannelLogger/",
                    str(history) + "/",
                ],
                check=True,
            )
        elif exists.returncode != 1:
            exists.check_returncode()
        acknowledgements = {
            "logs/ChannelLogger/" + str(p.relative_to(history)): digest(p)
            for p in history.rglob("*.gz")
            if not p.is_symlink()
        }
        # Receipts can only remove local files whose current hash matches the Mac copy.
        command = """python3 -c 'import json,sys,pathlib; p=pathlib.Path("/home/avinson/nishbot-recovery/archive-receipts.json"); d=json.loads(p.read_text()); d["history"]=json.load(sys.stdin); q=p.with_suffix(".next"); q.write_text(json.dumps(d)); q.chmod(384); q.replace(p)'"""
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", HOST, command],
            input=json.dumps(acknowledgements).encode(),
            check=True,
        )
        status = {
            "synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "verified_snapshot_files": len(manifest["files"]),
            "history_files": len(acknowledgements),
        }
        (destination / "sync-status.json").write_text(json.dumps(status, indent=2))
        print(json.dumps(status))


if __name__ == "__main__":
    main()
