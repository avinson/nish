# Working on Nishbot

Follow @/Users/avinson/.codex/RTK.md on this Mac. Prefix shell commands with
`rtk`; use `rtk proxy <command>` when RTK has no suitable wrapper or when exact
output matters. On other hosts, read that file if available; it is not deployed
to drebin. Do not install RTK on the server merely to run repository scripts.

## Source and runtime

- This repository contains source and operations tooling. The production checkout
  is `/home/avinson/git/avinson/nish` on `avinson@drebin`.
- `nishbot.service` runs that checkout's `.venv/bin/supybot` using the private
  `/home/avinson/nishbot/nishbot.conf`. State is under that runtime directory's
  `data`, `conf`, `logs`, and `backup` directories, outside Git.
- The bot uses `!` commands and joins `#darwin`, `#nish`, and `#xelpers` on Skub.
  TLS connects to `irc.darwin.network:6697` with certificate verification. The
  old `irc.skub.club` alias does not match the certificate.
- Compare local/remote Git revisions **and tree contents** before changing
  production; a merge commit can have a different ID but identical source.
- Drebin's login shell is fish. Send Bash scripts with `ssh drebin bash -s`,
  or use `tools/remote.sh` for ordinary remote commands. Bash heredocs and brace
  expansion cannot be assumed in the remote login shell.

## Development and checks

- Python 3.12, Limnoria 2026.10.4, and Cobe 3.0.1 are locked in `uv.lock`.
  Use `uv`, not ad hoc pip installs. Cobe intentionally overrides its old pins
  with PyStemmer 3.1.0 and irc 20.5.0; preserve its algorithm and schema.
- `rtk task deps:sync`, `rtk task test`, and `rtk task lint` install/check the
  frozen environment. Use `rtk proxy env UV_CACHE_DIR=/tmp/nish-uv-cache ...`
  if the normal uv cache is not writable in the sandbox.
- Tests isolate Limnoria's state with `tests/conftest.py`. Use its IRC harness
  for routing checks and mocked HTTP for previews. Never test against a live
  channel or production database unless the task calls for that.
- `requirements.txt`, Docker files, Titler, and I18nPlaceholder are legacy;
  the native deployment uses `pyproject.toml` and `uv.lock`.

## Plugin changes

- `tools/configure.py` has an explicit `ENABLED` allowlist. Update it and
  `nishbot.conf.tmpl` when adding plugins; otherwise config regeneration removes
  their settings. Preserve private credentials and existing channel overrides.
- SpiffyTitles has pinned upstream files and local integration code. Read
  `plugins/SpiffyTitles/PROVENANCE.md` before updating it. Keep its license and
  record the source commit. Review/test handlers before enabling more sites.
- Preview defaults pilot in `#nish`; `channelWhitelist` controls promotion.
  YouTube works through oEmbed without a key; rich metadata needs a YouTube
  Data API key. Optional OMDb enables IMDb metadata. Keys belong only in private
  runtime config or mode-600 `conf/youtube-api-key` and `conf/omdb-api-key` files.
- QuoteGrabs and Later are bundled Limnoria plugins. Later messages are public
  and nickname based. Include their state in normal runtime backups.
- Keep HTTP outside the IRC event loop, queues/caches bounded, failures quiet,
  and IRC output short. Do not log API keys, complete request exceptions, or
  private URLs. Test preview/command precedence against Cobe and Infobot.
- Preserve Cobe's 1% automatic reply rate, ten-second cooldown, delayed replies,
  nickname/marker filtering, and no self-learning. Preserve Infobot's customized
  learning/question behavior and Seen's Unicode-safe legacy reader.

## Operations and recovery

- `rtk task bot:status` and `rtk task bot:logs` inspect production. Logs may still
  contain private conversation text; do not paste raw history into outputs.
- `rtk task backup:create` creates a consistent recovery snapshot;
  `rtk task backup:sync` verifies and copies recovery/history to this Mac.
  Recovery lives at `/home/avinson/nishbot-recovery/current`; Mac archives live
  under `~/nishbot-archive/drebin`.
- `rtk task bot:deploy` tests the clean, committed **remote** checkout, snapshots
  state, stops the bot, regenerates its private configuration, and starts it.
  It does not pull or publish Git changes. Synchronize the intended revision
  explicitly first. Inspect service health and IRC connectivity afterward.
- Deployment saves the previous configuration as
  `/home/avinson/nishbot/backup/nishbot.pre-deploy.conf`. Its failure handler
  restores config and restarts using the current source; it is not a code rollback.
- `rtk task bot:rollback` is the **legacy Python 2 rollback**, not the normal
  undo for a plugin change. It restores pre-upgrade state and discards later
  learning, while saving failed state separately. Use the prior source revision
  and matching saved config for an ordinary plugin rollback, with the bot stopped.
- Never delete/retrain/replace live brains, factoids, Karma, Seen, QuoteGrabs,
  Later, or Quassel state as an incidental fix. Never commit runtime state or
  credentials. `history:evaluate` builds a separate evaluation model.
- `cleanup:plan` previews retention; `cleanup:apply` only removes recognized
  history/backups with verified Mac archive receipts. Preserve that restriction.
  `disk:status` checks the 2 GiB / 10% floor. An offline Mac can delay pruning.
