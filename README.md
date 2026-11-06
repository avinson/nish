# Nishbot

The deployed bot runs as `nishbot.service` on drebin. Runtime state lives in
`/home/avinson/nishbot`. This repository holds code and operations files.

Use `task --list` for common operations. Remote tasks default to
`avinson@drebin`; override with `task bot:status HOST=avinson@another-host`.

```sh
task deps:sync
task test
task lint
task bot:status
task bot:logs
task disk:status
task cleanup:plan
task backup:create
task backup:sync
```

`task cleanup:apply` deletes only recognized old backups with verified Mac
archive receipts. It keeps the latest ten backups in each filename family.
It never removes live brains, Infobot, Karma, Seen, or Quassel databases.
`task bot:deploy` tests and restarts the clean, committed remote checkout.
It does not pull or publish Git changes. `task bot:rollback` stops the new
service and restores the exact pre-upgrade state for the Python 2 runtime.
Rollback discards new learning from the restored state; it saves the failed
state separately for review.

## Runtime

Python 3.12, Limnoria 2026.10.4, and cobe 3.0.1 are locked in `uv.lock`.
cobe's source and schema stay unchanged. uv overrides its old dependency
pins with tested PyStemmer 3.1.0 and irc 20.5.0. Use `uv`, rather than pip,
to reproduce this intentional dependency exception.

Infobot retains its customized passive-learning and question behavior. It
uses separate SQLite3 databases per channel. Karma and Seen use Limnoria's
bundled behavior. A thin Seen adapter reads legacy Unicode CSV records without splitting their messages at Unicode line separators. Disabled legacy plugins and Docker files are not
part of this native deployment.

The bot connects to `irc.darwin.network:6697` with certificate verification.
The old alias `irc.skub.club` does not match the server certificate.
Credentials stay in the private runtime configuration, outside Git.

Cobe learns accepted incoming channel messages, not its own output. It
removes whole nickname tokens and rejects either old reserved marker on
input. Every Cobe output path removes historical marker prefixes and current
nicknames. Existing brain history stays intact. `probability=100` means a 1% automatic reply chance. Automatic replies have a ten-second cooldown. Addressed replies can
bypass it. Replies are delayed by two to five seconds when configured.

## Recovery and retention

Daily cron jobs run cleanup at 02:17 and a consistent SQLite snapshot at
02:37, in the host timezone. An hourly disk check records a low-space status
below 2 GiB or 10% free. Logrotate checks hourly; operational logs retain ten
compressed rotations of up to 25 MB each. The journal has a 512 MB cap and
a 30-day retention limit.

The rolling recovery copy is `/home/avinson/nishbot-recovery/current`.
Snapshots require replacement space plus a 1 GiB reserve. The snapshot
includes channel databases, credentials, Seen, and a consistent Quassel copy.
The immutable pre-upgrade archive is kept separately for rollback.

This Mac stores protected archives under `~/nishbot-archive/drebin`.
A LaunchAgent retries synchronization when the Mac is awake. Synchronization
verifies every snapshot hash and keeps current and previous copies. It
acknowledges only closed, compressed history files present on the Mac.
Cleanup cannot prune unacknowledged history. Check `sync-status.json` for
the last successful transfer. An offline Mac can therefore delay pruning;
disk checks expose that condition without deleting unarchived history.

## Offline retraining

`task history:export` merges the archived #darwin logs, Quassel, and the old
bot log. It excludes known nish output and commands, rejects marker text,
and deduplicates overlapping minute/sender/message observations. Repeated
identical messages from one sender within a minute collapse into one entry.

`task history:evaluate` builds a separate Markovify model and records timing,
sample success, and private sample text. It does not change the live model.
The available logs miss March 2018 through July 2023, a November 2017 gap,
and possible earlier or imported training. Retraining cannot preserve all
of the old personality. Read the private evaluation reports before replacing
the deployed brain.
