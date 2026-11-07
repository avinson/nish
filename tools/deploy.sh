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
/home/avinson/.local/bin/uv run --frozen ruff check plugins/Cobe plugins/Infobot plugins/Seen plugins/SpiffyTitles tools tests
.venv/bin/python tools/maintenance.py snapshot --apply
root=/home/avinson/nishbot
candidate=$(mktemp "$root/conf/.deploy-config.XXXXXX")
previous="$root/backup/nishbot.pre-deploy.conf"
saved=false
recover() {
  status=$?
  trap - ERR
  set +e
  sudo systemctl stop nishbot
  if "$saved"; then install -m 600 "$previous" "$root/nishbot.conf"; fi
  sudo systemctl restart nishbot
  rm -f "$candidate"
  exit "$status"
}
trap recover ERR
# Stop first so Limnoria flushes its latest settings before regeneration.
sudo systemctl stop nishbot
install -m 600 "$root/nishbot.conf" "$previous"
saved=true
args=()
if test -f "$root/conf/youtube-api-key"; then
  args+=(--youtube-key-file "$root/conf/youtube-api-key")
fi
if test -f "$root/conf/omdb-api-key"; then
  args+=(--omdb-key-file "$root/conf/omdb-api-key")
fi
.venv/bin/python tools/configure.py "$root/nishbot.conf" "$candidate" "${args[@]}"
install -m 600 "$candidate" "$root/nishbot.conf"
sudo systemctl start nishbot
sleep 3
sudo systemctl is-active --quiet nishbot
trap - ERR
rm -f "$candidate"
git rev-parse HEAD
