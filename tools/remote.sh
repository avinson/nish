#!/usr/bin/env bash
# Run service operations locally on drebin, or through explicit SSH from a Mac.
set -euo pipefail
host=$1
shift
if test "$(hostname -s)" = drebin && test "$host" = avinson@drebin && test "$(id -un)" = avinson; then
  exec bash -c "$*"
fi
exec ssh -o BatchMode=yes "$host" "$@"
