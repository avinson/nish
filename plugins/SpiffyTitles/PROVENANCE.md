# SpiffyTitles provenance and Nishbot integration

Source: https://github.com/matiasw/my-limnoria-plugins/tree/2661b9f13582379a7a4b00fddbe359098b351c96/SpiffyTitles

Pinned commit: `2661b9f13582379a7a4b00fddbe359098b351c96`.

`upstream.py` is the unmodified upstream `plugin.py`. `README.md`, `_version.py`,
`pyproject.toml`, and `requirements.txt` retain their upstream contents. The
BSD 3-clause license is retained in the source headers and copied to `LICENSE`.
These packaging files document provenance; install dependencies through the
repository root's `pyproject.toml` and `uv.lock`, not pip in this directory.

Local changes:

- `__init__.py` exports the local adapter without importing upstream's missing
  test module. `config.py` changes defaults to the `#nish` pilot, short templates,
  single-link output, silent failures, and disabled unreviewed handlers; it adds
  a per-user/channel cooldown and narrows the i18n import exception.
- `plugin.py` subclasses upstream, retaining configuration and template helpers.
  It replaces event routing, fetching, caching, YouTube and IMDb handlers. A
  bounded worker queue claims preview messages before Cobe's passive callback;
  duplicate video URLs share a bounded ten-minute cache. `!t URL` can repeat a
  cached preview and uses the same cooldown and channel restrictions.
- Requests validate public destinations and redirects, cap bodies at 1 MiB,
  and use five-second socket/read limits. Output strips IRC controls and stays
  within 380 UTF-8 bytes. Failures never print request exceptions or credentials.
- YouTube uses the Data API when configured, falling back to oEmbed for title
  and uploader. IMDb uses HTTPS OMDb only when configured/enabled. Other site
  handlers remain inactive in the adapter even if their upstream toggles change.

To update: inspect the upstream diff from this commit, replace the unmodified
files, reapply the documented config/package integration, and run the full
regression and lint tasks. Review handlers independently before exposing them.
Retain the copyright/license and update this pin. Do not auto-update production.
