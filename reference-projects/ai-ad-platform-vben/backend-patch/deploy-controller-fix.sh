#!/usr/bin/env bash
set -euo pipefail

KEY=/d/finalshell/pem/adpulse-power.pem
HOST=ubuntu@44.228.249.36

scp -i "$KEY" -o StrictHostKeyChecking=no \
  backend-patch/src/com/adpulse/system/asset/controller/DynamicAssetFlowController.java \
  "$HOST:/home/ubuntu/adpulse-v8/src/DynamicAssetFlowController.java"

ssh -i "$KEY" -o StrictHostKeyChecking=no "$HOST" <<'REMOTE'
set -euo pipefail
WORK=/home/ubuntu/adpulse-v8
APP=/opt/docker/java/system
RELEASE="$(date +%Y%m%d%H%M%S)"

docker run --rm -v "$WORK:/work" -w /work eclipse-temurin:21-jdk \
  bash -lc 'rm -rf compiled && mkdir -p compiled && javac -parameters -cp "extracted/BOOT-INF/classes:extracted/BOOT-INF/lib/*" -d compiled src/DynamicAssetFlowController.java'

BASE_JAR="$(ls -1t "$APP"/backups/*.v8.1-pre.bak | head -n 1)"
rm -f "$WORK/adpulse-system-server-v8.1.jar"
cp "$BASE_JAR" "$WORK/adpulse-system-server-v8.1.jar"
rm -rf "$WORK/staging"
mkdir -p "$WORK/staging/BOOT-INF/classes"
cp -R "$WORK/compiled/com" "$WORK/staging/BOOT-INF/classes/com"
docker run --rm -v "$WORK:/work" -w /work eclipse-temurin:21-jdk \
  jar uf adpulse-system-server-v8.1.jar -C staging BOOT-INF/classes/com
cp "$WORK/adpulse-system-server-v8.1.jar" "$APP/adpulse-system-server.jar"

cd "$APP"
docker build --tag adpulse-system-server:v8.1 .
docker rm --force adpulse-system-server >/dev/null 2>&1 || true
docker run --detach \
  --name adpulse-system-server \
  --restart unless-stopped \
  --network docker_default \
  --env-file "$APP/conf/application.env" \
  --publish 0.0.0.0:8080:8080 \
  --volume "$APP/logs:/opt/docker/java/system/logs" \
  adpulse-system-server:v8.1 >/dev/null

for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8080/api/v3/api-docs | grep -q '/asset-flow-v2/applications'; then
    echo "BACKEND_RELEASE=$RELEASE"
    echo "BACKEND_HEALTH=OK"
    exit 0
  fi
  sleep 2
done

echo 'v8.1 health check failed; rolling back container image' >&2
docker rm --force adpulse-system-server >/dev/null 2>&1 || true
docker run --detach \
  --name adpulse-system-server \
  --restart unless-stopped \
  --network docker_default \
  --env-file "$APP/conf/application.env" \
  --publish 0.0.0.0:8080:8080 \
  --volume "$APP/logs:/opt/docker/java/system/logs" \
  adpulse-system-server:v8 >/dev/null
exit 1
REMOTE
