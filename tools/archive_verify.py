"""Verify every archived legacy backup before issuing deletion receipts."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def main():
    """Compare archive members with hashes read directly from drebin."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("receipts", type=Path)
    args = parser.parse_args()
    expected = {}
    for line in args.manifest.read_text().splitlines():
        digest, path = line.split("  ", 1)
        expected["nishbot/backup/" + Path(path).name] = digest
    actual = {}
    with tarfile.open(args.archive, "r|gz") as tar:
        for member in tar:
            if member.name in expected:
                if not member.isfile():
                    raise ValueError("Backup member is not a regular file")
                digest = hashlib.file_digest(tar.extractfile(member), "sha256").hexdigest()
                if digest != expected[member.name]:
                    raise ValueError("Archive hash mismatch: " + member.name)
                actual[member.name] = digest
    assert actual == expected
    receipt = {"archive": str(args.archive), "files": {Path(k).name: v for k, v in actual.items()}}
    args.receipts.write_text(json.dumps(receipt, indent=2))
    args.receipts.chmod(0o600)
    print(json.dumps({"verified_backups": len(actual), "receipts": str(args.receipts)}))


if __name__ == "__main__":
    main()
