#!/usr/bin/env bash
set -euo pipefail

ssh -i /d/finalshell/pem/adpulse-power.pem \
  -o StrictHostKeyChecking=no \
  ubuntu@44.228.249.36 \
  "docker exec -i adpulse-system-mysql sh -lc 'exec mysql -u\"\$MYSQL_USER\" -p\"\$MYSQL_PASSWORD\" \"\$MYSQL_DATABASE\"' < /home/ubuntu/adpulse-v8/V8__dynamic_asset_flow.sql"
