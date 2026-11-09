root@ip-172-31-34-92:/home/ubuntu/code/schedulers# docker exec -it broker bash
broker:/pulsar$ bin/pulsar tokens create --private-key /pulsar/data/jwt-private.key --subject test
REDACTED_REFERENCE_SECRET

broker:/pulsar$ bin/pulsar-admin --auth-plugin org.apache.pulsar.client.impl.auth.AuthenticationToken --auth-params token:REDACTED_REFERENCE_SECRET namespaces create public/ads

broker:/pulsar$ bin/pulsar-admin --auth-plugin org.apache.pulsar.client.impl.auth.AuthenticationToken --auth-params token:REDACTED_REFERENCE_SECRET topics create persistent://public/ads/ad-operation
broker:/pulsar$ bin/pulsar-admin \
--admin-url "http://localhost:8080/" \
--auth-params {"token":"REDACTED_REFERENCE_SECRET"} \
--auth-plugin "org.apache.pulsar.client.impl.auth.AuthenticationToken" \
namespaces grant-permission public/ads --role test --actions produce,consume
