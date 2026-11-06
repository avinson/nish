#!/usr/bin/env bash
# Restore the isolated pre-upgrade data, not a database shared between runtimes.
set -euo pipefail
root=/home/avinson/nishbot
archive=/home/avinson/nishbot-recovery/pre-upgrade.tar.gz
test -r "$archive"
cd /home/avinson/nishbot-recovery
sha256sum -c pre-upgrade.sha256
if systemctl cat nishbot >/dev/null 2>&1; then
  sudo systemctl stop nishbot
fi
stamp=$(date +%Y%m%dT%H%M%S)
mkdir -m 700 "failed-$stamp"
mv "$root/data" "$root/conf" "$root/nishbot.conf" "failed-$stamp/"
tar -xzf "$archive" -C "$root"
if systemctl cat nishbot >/dev/null 2>&1; then
  sudo systemctl disable nishbot >/dev/null
fi
cd "$root"
nohup /usr/bin/python2 /home/avinson/.local/bin/supybot "$root/nishbot.conf" >"$root/logs/rollback-console.log" 2>&1 </dev/null &
echo "Legacy bot started with PID $!; failed state kept in failed-$stamp."
