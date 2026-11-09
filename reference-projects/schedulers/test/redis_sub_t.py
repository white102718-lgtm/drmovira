import json

from db.clients import redis_cli

redis_cli.publish("adsservice:events.ads_handle", json.dumps(json.dumps({
  "auto_run": True,
  "dev_id": "61567004428837",
  "id": "120231259486920781",
  "is_send": True,
  "level": "campaign",
  "type": "start"
})))
