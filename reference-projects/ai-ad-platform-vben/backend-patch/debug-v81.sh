#!/usr/bin/env bash
set -euo pipefail

ssh -i /d/finalshell/pem/adpulse-power.pem -o StrictHostKeyChecking=no ubuntu@44.228.249.36 <<'REMOTE'
set -e
docker rm --force adpulse-v81-debug >/dev/null 2>&1 || true
docker run --detach \
  --name adpulse-v81-debug \
  --network docker_default \
  --env-file /opt/docker/java/system/conf/application.env \
  --publish 127.0.0.1:18081:8080 \
  adpulse-system-server:v8.1 >/dev/null
sleep 12
docker ps -a --filter name=adpulse-v81-debug --format '{{.Status}}'
docker logs --tail 180 adpulse-v81-debug 2>&1
docker rm --force adpulse-v81-debug >/dev/null 2>&1 || true
REMOTE
