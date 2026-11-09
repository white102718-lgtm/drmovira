#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

DEPLOY_HOST="${DEPLOY_HOST:-44.228.249.36}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"
DEPLOY_USER="${DEPLOY_USER:-ubuntu}"
SSH_KEY="${SSH_KEY:-}"
REMOTE_DIR="${REMOTE_DIR:-/opt/docker/java/system}"
CONTAINER_NAME="${CONTAINER_NAME:-adpulse-system-server}"
IMAGE_NAME="${IMAGE_NAME:-adpulse-system-server:0.1.0}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/api/v3/api-docs}"
MAVEN_CMD="${MAVEN_CMD:-mvn}"
SKIP_BUILD="${SKIP_BUILD:-false}"

if [[ -z "$SSH_KEY" ]]; then
  if [[ -f "D:/finalshell/pem/adpulse-power.pem" ]]; then
    SSH_KEY="D:/finalshell/pem/adpulse-power.pem"
  elif [[ -f "/mnt/d/finalshell/pem/adpulse-power.pem" ]]; then
    SSH_KEY="/mnt/d/finalshell/pem/adpulse-power.pem"
  fi
fi

if [[ -z "$SSH_KEY" || ! -f "$SSH_KEY" ]]; then
  echo "SSH 密钥不存在：$SSH_KEY" >&2
  exit 1
fi

command -v ssh >/dev/null || { echo "未找到 ssh" >&2; exit 1; }
command -v scp >/dev/null || { echo "未找到 scp" >&2; exit 1; }

if [[ "$SKIP_BUILD" != "true" ]]; then
  echo "[1/5] 格式化、测试并打包"
  if [[ "$MAVEN_CMD" == */* ]]; then
    [[ -x "$MAVEN_CMD" ]] || { echo "Maven 不可执行：$MAVEN_CMD" >&2; exit 1; }
  else
    command -v "$MAVEN_CMD" >/dev/null || { echo "未找到 Maven：$MAVEN_CMD" >&2; exit 1; }
  fi
  (
    cd "$PROJECT_DIR"
    "$MAVEN_CMD" spotless:apply verify
  )
else
  echo "[1/5] 跳过构建，使用 target 中已有 JAR"
fi

JAR_PATH="$PROJECT_DIR/adpulse-system/target/adpulse-system-server.jar"
if [[ ! -f "$JAR_PATH" ]]; then
  echo "未找到当前构建产物：$JAR_PATH" >&2
  exit 1
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
REMOTE_CANDIDATE="/tmp/${CONTAINER_NAME}-${TIMESTAMP}.jar"
SSH_TARGET="${DEPLOY_USER}@${DEPLOY_HOST}"
SSH_OPTIONS=(-i "$SSH_KEY" -p "$DEPLOY_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
SCP_OPTIONS=(-i "$SSH_KEY" -P "$DEPLOY_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)

echo "[2/5] 上传应用包"
scp "${SCP_OPTIONS[@]}" "$JAR_PATH" "${SSH_TARGET}:${REMOTE_CANDIDATE}"

echo "[3/5] 备份并构建测试环境镜像"
echo "[4/5] 切换容器并执行健康检查"
ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" bash -s -- \
  "$REMOTE_DIR" "$CONTAINER_NAME" "$IMAGE_NAME" "$REMOTE_CANDIDATE" \
  "$TIMESTAMP" "$HEALTH_URL" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

REMOTE_DIR="$1"
CONTAINER_NAME="$2"
IMAGE_NAME="$3"
REMOTE_CANDIDATE="$4"
TIMESTAMP="$5"
HEALTH_URL="$6"
APP_JAR="$REMOTE_DIR/adpulse-system-server.jar"
BACKUP_DIR="$REMOTE_DIR/backups"
BACKUP_JAR="$BACKUP_DIR/adpulse-system-server.jar.${TIMESTAMP}.bak"
ROLLBACK_CONTAINER="${CONTAINER_NAME}-rollback-${TIMESTAMP}"
OLD_CONTAINER_EXISTS=false

command -v docker >/dev/null || { echo "服务器未安装 Docker" >&2; exit 1; }
command -v curl >/dev/null || { echo "服务器未安装 curl" >&2; exit 1; }
test -f "$REMOTE_DIR/Dockerfile" || { echo "缺少 Dockerfile" >&2; exit 1; }
test -f "$REMOTE_DIR/conf/application.env" || { echo "缺少 application.env" >&2; exit 1; }
test -f "$REMOTE_CANDIDATE" || { echo "上传的 JAR 不存在" >&2; exit 1; }
grep -q '^FILE_STORAGE_ROOT=' "$REMOTE_DIR/conf/application.env" || {
  echo "application.env 缺少 FILE_STORAGE_ROOT" >&2
  exit 1
}

mkdir -p "$BACKUP_DIR"
install -d -m 0750 "$REMOTE_DIR/files"
if [[ -f "$APP_JAR" ]]; then
  cp "$APP_JAR" "$BACKUP_JAR"
fi
install -m 0644 "$REMOTE_CANDIDATE" "$APP_JAR"
rm -f "$REMOTE_CANDIDATE"

rollback() {
  local exit_code=$?
  trap - ERR
  echo "发布失败，正在回滚" >&2
  docker rm --force "$CONTAINER_NAME" >/dev/null 2>&1 || true
  if [[ "$OLD_CONTAINER_EXISTS" == "true" ]]; then
    docker rename "$ROLLBACK_CONTAINER" "$CONTAINER_NAME"
    docker start "$CONTAINER_NAME" >/dev/null
  fi
  if [[ -f "$BACKUP_JAR" ]]; then
    cp "$BACKUP_JAR" "$APP_JAR"
  fi
  exit "$exit_code"
}
trap rollback ERR

docker build --tag "$IMAGE_NAME" "$REMOTE_DIR"

if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  docker rename "$CONTAINER_NAME" "$ROLLBACK_CONTAINER"
  docker stop "$ROLLBACK_CONTAINER" >/dev/null
  OLD_CONTAINER_EXISTS=true
fi

docker run --detach \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --network docker_default \
  --env-file "$REMOTE_DIR/conf/application.env" \
  --publish 0.0.0.0:8080:8080 \
  --volume "$REMOTE_DIR/logs:/opt/docker/java/system/logs" \
  --volume "$REMOTE_DIR/files:/opt/docker/java/system/files" \
  "$IMAGE_NAME" >/dev/null

HEALTHY=false
for _ in $(seq 1 30); do
  if curl --fail --silent --show-error "$HEALTH_URL" >/dev/null; then
    HEALTHY=true
    break
  fi
  sleep 2
done
[[ "$HEALTHY" == "true" ]] || { echo "健康检查超时：$HEALTH_URL" >&2; false; }

trap - ERR
if [[ "$OLD_CONTAINER_EXISTS" == "true" ]]; then
  docker rm "$ROLLBACK_CONTAINER" >/dev/null
fi
docker ps --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}} {{.Status}} {{.Ports}}'
REMOTE_SCRIPT

echo "[5/5] 发布成功：http://${DEPLOY_HOST}:8080/api"
