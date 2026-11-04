#!/usr/bin/env sh
# Fails if LiveKit shows up anywhere in the project: code, dependencies, config or docs.
# Ulai Voice Studio runs entirely on Ulai Voice Infra. The checkers themselves are the only exception.
set -eu
cd "$(dirname "$0")/.."
hits=$(grep -rniI "livekit" . \
    --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=.venv \
    --exclude-dir=__pycache__ --exclude='check-no-livekit.*' | grep -vi "no-livekit" || true)
if [ -n "$hits" ]; then
  echo "$hits"
  echo "LiveKit reference found (above). Remove it." >&2
  exit 1
fi
echo "No LiveKit references."
