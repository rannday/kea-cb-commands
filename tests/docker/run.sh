#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# Keep buildx's writable client state in the ignored build layout, not ~/.docker.
DOCKER_CONFIG=${DOCKER_CONFIG:-"$root/build/docker/client"}
export DOCKER_CONFIG
mkdir -p "$DOCKER_CONFIG"
compose() { docker compose -f "$root/tests/docker/compose.yml" "$@"; }
case "${1:-test}" in
    start)
        compose config --quiet
        compose build
        compose up -d --wait postgres mariadb
        ;;
    test)
        "$0" start
        set +e
        compose up --no-deps --force-recreate --abort-on-container-exit --exit-code-from kea kea
        result=$?
        set -e
        mkdir -p "$root/build/docker/results"
        compose logs --no-color > "$root/build/docker/results/compose.log"
        compose cp kea:/evidence/. "$root/build/docker/results/" || result=1
        exit "$result"
        ;;
    diagnostics) compose ps -a; compose logs --no-color --tail 100 ;;
    stop) compose down ;;
    clean) compose down --volumes ;;
    *) echo "Usage: $0 {start|test|diagnostics|stop|clean}" >&2; exit 2 ;;
esac
