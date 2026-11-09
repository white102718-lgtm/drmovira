#!/usr/bin/env bash
set -euo pipefail

ssh -i /d/finalshell/pem/adpulse-power.pem -o StrictHostKeyChecking=no ubuntu@44.228.249.36 <<'REMOTE'
docker inspect -f '{{.Config.Image}}' adpulse-system-server
docker ps -a --filter name=adpulse-system-server --format '{{.Image}} {{.Status}}'
docker inspect -f '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' adpulse-system-server
docker inspect -f '{{json .Config.Labels}}' adpulse-system-server
docker inspect -f 'cmd={{json .Config.Cmd}} entry={{json .Config.Entrypoint}} restart={{.HostConfig.RestartPolicy.Name}} network={{.HostConfig.NetworkMode}} ports={{json .HostConfig.PortBindings}}' adpulse-system-server
ls -la /opt/docker/java/system
if [ -f /opt/docker/java/system/Dockerfile ]; then sed -n '1,120p' /opt/docker/java/system/Dockerfile; fi
sed -n '1,220p' /opt/docker/java/system/docker-start.sh
docker logs --tail 100 adpulse-system-server 2>&1
ls -lt /opt/docker/java/system/backups | head -n 12
docker run --rm -v /opt/docker/java/system/backups:/backups eclipse-temurin:21-jdk \
  bash -lc 'for f in /backups/*.v8.1-pre.bak /backups/*.v8-pre.bak; do echo "JAR=$f"; jar tf "$f" | grep DynamicAssetFlowController | head -n 8; done'
REMOTE
