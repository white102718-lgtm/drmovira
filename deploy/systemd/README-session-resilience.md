# API dependency resilience

On 2026-11-12 an unattended MySQL upgrade stopped orbit-api through its
`Requires=mysql.service redis-server.service` relationship. A successful dependency
stop does not trigger `Restart=on-failure`, leaving nginx returning 502.

In the base `/etc/systemd/system/orbit-api.service` replace that Requires line with:

```ini
Wants=mysql.service redis-server.service
```

Keep `After=network.target mysql.service redis-server.service`. Run
`systemctl daemon-reload`, then verify `systemctl show orbit-api -p Requires -p Wants`.
MySQL and Redis must appear only in Wants, not Requires. An empty Requires in a
drop-in cannot remove these dependencies; edit the base unit. Preserve a backup.

If the API is already inactive, start it and verify `/captchaImage` locally and
`/prod-api/captchaImage` through HTTPS. No database migration or session TTL change.
Isolated sleep-service verification reproduced the Requires stop and confirmed the
Wants service stayed active after stopping its dependency. Production DB was not
restarted for this test. Security updates remain enabled.

## Frontend release continuity

Before switching nginx root to a new web release, copy the previous release's
hashed `static/` files into the new release without overwriting new files. Keep at
least the immediately previous version for existing browser tabs. Serve index.html
with `Cache-Control: no-cache` and preserve existing security headers. Use
`location /static/ { try_files $uri =404; }` so a missing JS file never receives
index.html with status 200. Validate nginx configuration before reload.
