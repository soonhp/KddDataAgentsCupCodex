#!/usr/bin/env bash
set -euo pipefail
TEAM_ID="${TEAM_ID:-kdddataagents}"
VERSION="${VERSION:-v1}"
IMAGE="${TEAM_ID}:${VERSION}"
docker build --platform linux/amd64 -t "${IMAGE}" .
echo "Built ${IMAGE}"
