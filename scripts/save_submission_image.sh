#!/usr/bin/env bash
set -euo pipefail
TEAM_ID="${TEAM_ID:-kdddataagents}"
VERSION="${VERSION:-v1}"
IMAGE="${TEAM_ID}:${VERSION}"
ARCHIVE="${TEAM_ID}_${VERSION}.tar.gz"
docker save "${IMAGE}" | gzip -c > "${ARCHIVE}"
ls -lh "${ARCHIVE}"
echo "Saved ${ARCHIVE} with docker save"
