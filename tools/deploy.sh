#!/usr/bin/env bash
# Deploy only a tested, committed checkout. Runtime state stays outside Git.
set -euo pipefail
cd /home/avinson/git/avinson/nish
if test -n "$(git status --porcelain --untracked-files=no)"; then
  echo 'Commit tracked source changes before deployment.' >&2
  exit 1
fi
/home/avinson/.local/bin/uv sync --frozen
/home/avinson/.local/bin/uv run --frozen pytest -q
/home/avinson/.local/bin/uv run --frozen ruff check plugins/Cobe plugins/Infobot tools tests
.venv/bin/python tools/maintenance.py snapshot --apply
sudo systemctl restart nishbot
sleep 3
sudo systemctl is-active --quiet nishbot
git rev-parse HEAD
