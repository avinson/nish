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
nicknames. Existing brain history stays intact. `probability=200` means a 2%
automatic reply selection chance. Automatic replies have a ten-second cooldown.
Addressed replies can bypass it. Replies are delayed by two to five seconds when
configured.

Cobe logs aggregate automatic reply counts hourly and on shutdown without message
contents. `eligible` counts ordinary messages reaching the random roll;
`expected_rolls` is the sum of their configured probabilities, and `selected`
is the number chosen. The remaining counts show submission rejection, cooldown,
empty or unavailable output, messages queued for IRC, and worker failures. A
delayed reply may be counted in a later interval than its selection; queued
messages are not confirmation of delivery. Use `task bot:logs` to inspect them.

## Previews, quotes, and messages

SpiffyTitles is vendored at a reviewed upstream revision with a Nishbot adapter;
see `plugins/SpiffyTitles/PROVENANCE.md` for the pin and local changes. Preview
defaults pilot in `#nish`. They show one compact title per message, suppress
duplicate URLs for ten minutes, and apply a five-second per-user cooldown.
`!t URL` repeats a cached preview. Other channels stay quiet until added to
`supybot.plugins.SpiffyTitles.channelWhitelist` (a comma-separated channel list).

YouTube titles and uploaders work without a key through oEmbed. To add duration,
views, and upload date, enable the YouTube Data API in your Google project and
save its API key privately on drebin in
`/home/avinson/nishbot/conf/youtube-api-key` (mode 600). Optional IMDb metadata
uses an OMDb key saved as `conf/omdb-api-key`; deployment enables that handler
when it imports this file. Never paste keys into channel messages or Git.
`task bot:deploy` imports these files without printing their contents. Existing
keys in private runtime config survive regeneration. API failures fall back to
oEmbed where possible; unavailable links produce no automatic error message.
Other specialized site handlers are inactive pending separate review.

Bundled QuoteGrabs and Later provide:

```text
!grab alice                         capture Alice's most recent channel message
!quote alice                        recall Alice's latest captured quote
!quotegrabs random                  recall a random captured quote
!later tell alice the movie is on   deliver when Alice next speaks
!later undo alice                   cancel your last pending message to Alice
```

Later messages are public and identify recipients by nickname. Quotes are
stored per channel. Both plugins' persistent state is included in recovery
snapshots. Existing Cobe, Infobot, Karma, and Seen behavior stays intact.

Deployment tests and snapshots before stopping the bot to regenerate its
private config. The prior config is saved as `backup/nishbot.pre-deploy.conf`.
On failure the deployment script restores that config and restarts the current
source; a code rollback still requires restoring the prior source revision.
The `bot:rollback` task is specifically the legacy Python 2 recovery procedure.

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
