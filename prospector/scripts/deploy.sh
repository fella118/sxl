#!/usr/bin/env bash
# Roll out the latest image built by GitHub Actions, then verify every connection.
# usage: scripts/deploy.sh user@server [/opt/sogixel]
set -euo pipefail
HOST=$1
DIR=${2:-/opt/sogixel}
ssh "$HOST" "cd $DIR && docker compose pull employee && docker compose up -d \
  && sleep 5 && docker compose exec -T employee python -m sogixel check --live"
