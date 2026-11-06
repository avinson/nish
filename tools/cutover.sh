#!/usr/bin/env bash
# Initial migration. Any failure restores the stopped legacy runtime.
set -euo pipefail
repo=/home/avinson/git/avinson/nish
root=/home/avinson/nishbot
recovery=/home/avinson/nishbot-recovery
cd "$repo"
test -r "$recovery/candidate.conf"
test ! -e "$recovery/pre-upgrade.tar.gz"
oldpid=$(pgrep -u avinson -f '^/usr/bin/python2 /home/avinson/.local/bin/supybot nishbot.conf$')
test -n "$oldpid"

recover() {
  trap - ERR
  if test -r "$recovery/pre-upgrade.sha256"; then
    bash "$repo/tools/rollback.sh"
  else
    cd "$root"
    nohup /usr/bin/python2 /home/avinson/.local/bin/supybot nishbot.conf >logs/rollback-console.log 2>&1 </dev/null &
  fi
}
trap recover ERR
kill -TERM "$oldpid"
for _ in $(seq 1 60); do
  if ! kill -0 "$oldpid" 2>/dev/null; then break; fi
  sleep 1
done
if kill -0 "$oldpid" 2>/dev/null; then
  echo 'Legacy bot did not stop. Abort before migration.' >&2
  trap - ERR
  exit 1
fi
tar -C "$root" -cf - data conf nishbot.conf plugins | gzip -1 > "$recovery/pre-upgrade.tar.gz.next"
mv "$recovery/pre-upgrade.tar.gz.next" "$recovery/pre-upgrade.tar.gz"
(cd "$recovery" && sha256sum pre-upgrade.tar.gz >pre-upgrade.sha256)
chmod 600 "$recovery/pre-upgrade.tar.gz" "$recovery/pre-upgrade.sha256"
echo 'Final legacy state archived; migrating copied record formats.'
.venv/bin/python tools/migrate.py "$root" > "$recovery/migration-report.json"
install -m 600 "$recovery/candidate.conf" "$root/nishbot.conf"
touch "$root/conf/networks.conf"
mv "$root/logs/messages.log" "$root/logs/messages.pre-upgrade.log"
find "$root/conf" "$root/data" -type d -exec chmod 700 {} +
find "$root/conf" "$root/data" -type f -exec chmod 600 {} +
chmod 700 "$root" "$root/logs"
sudo install -m 644 ops/nishbot.service /etc/systemd/system/nishbot.service
sudo install -m 644 ops/nishbot.logrotate /etc/logrotate-nishbot.conf
sudo install -m 644 ops/nishbot.cron /etc/cron.d/nishbot
sudo systemctl daemon-reload
sudo systemctl enable --now nishbot
sleep 5
sudo systemctl is-active --quiet nishbot
trap - ERR
echo 'New service is active. Validate IRC connection and migrated records.'
