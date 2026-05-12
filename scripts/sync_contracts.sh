#!/usr/bin/env bash
# Sync contracts/ from this backend repo into the training repos.
#
# todo.md #5: the schemas live here (single source of truth — payload schema
# is what the backend agrees to accept from the frontend) and the training
# pipelines (`trainer/extract.py`) consume the same files via this rsync.
#
# Run from the AntiFraudMain (Back) root.

set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
WEB="${HERE}/../AntiFraudMLWeb"
MOBILE="${HERE}/../AntiFraudMLMobile"

if [[ ! -d "${HERE}/contracts" ]]; then
  echo "error: ${HERE}/contracts not found" >&2
  exit 1
fi

for target in "${WEB}" "${MOBILE}"; do
  if [[ ! -d "${target}" ]]; then
    echo "warn: ${target} not present, skipping" >&2
    continue
  fi
  echo "syncing → ${target}/contracts/"
  mkdir -p "${target}/contracts"
  rsync -a --delete "${HERE}/contracts/" "${target}/contracts/"
done

echo "done"
