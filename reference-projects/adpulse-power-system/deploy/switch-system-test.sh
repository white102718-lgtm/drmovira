#!/usr/bin/env bash
set -Eeuo pipefail

remote_dir=/opt/docker/java/system
container=adpulse-system-server
image=adpulse-system-server:0.1.0
candidate=/tmp/adpulse-system-server-candidate.jar
timestamp="$(date +%Y%m%d-%H%M%S)"
rollback_container="${container}-rollback-${timestamp}"
app_jar="$remote_dir/adpulse-system-server.jar"
backup="$remote_dir/backups/adpulse-system-server.jar.${timestamp}.bak"
old_exists=false

cp /tmp/adpulse-system-build/adpulse-system/target/adpulse-system-server-0.1.0-SNAPSHOT.jar "$candidate"
mkdir -p "$remote_dir/backups"
install -d -m 0750 "$remote_dir/files"
grep -q '^FILE_STORAGE_ROOT=' "$remote_dir/conf/application.env"
[[ ! -f "$app_jar" ]] || cp "$app_jar" "$backup"
install -m 0644 "$candidate" "$app_jar"
docker build --tag "$image" "$remote_dir"

rollback() {
  trap - ERR
  docker rm --force "$container" >/dev/null 2>&1 || true
  if [[ "$old_exists" == true ]]; then
    docker rename "$rollback_container" "$container"
    docker start "$container" >/dev/null
  fi
  [[ ! -f "$backup" ]] || cp "$backup" "$app_jar"
  echo BACKEND_ROLLED_BACK >&2
  exit 1
}
trap rollback ERR

if docker container inspect "$container" >/dev/null 2>&1; then
  docker rename "$container" "$rollback_container"
  docker stop "$rollback_container" >/dev/null
  old_exists=true
fi

docker run --detach --name "$container" --restart unless-stopped \
  --network docker_default --env-file "$remote_dir/conf/application.env" \
  --publish 0.0.0.0:8080:8080 \
  --volume "$remote_dir/logs:/opt/docker/java/system/logs" \
  --volume "$remote_dir/files:/opt/docker/java/system/files" "$image" >/dev/null

healthy=false
for _ in $(seq 1 40); do
  if curl --fail --silent http://127.0.0.1:8080/api/v3/api-docs >/dev/null; then
    healthy=true
    break
  fi
  sleep 2
done
[[ "$healthy" == true ]]
trap - ERR
[[ "$old_exists" != true ]] || docker rm "$rollback_container" >/dev/null
docker ps --filter "name=^/${container}$" --format '{{.Names}} {{.Status}} {{.Ports}}'
echo BACKEND_DEPLOY_OK
