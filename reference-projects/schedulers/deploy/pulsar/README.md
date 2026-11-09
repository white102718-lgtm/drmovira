# standalone 是一个容器就可以启动pulsar的

docker-compose -f standalone-docker-compose.yml up -d

# 启动

注意需要挂载的容器有全部777权限
mkdir -p /opt/pulsar/data/{zookeeper,bookkeeper,broker} && chmod -R 777 /opt/pulsar/data

## 权限登录
步骤一：准备目录和权限

  mkdir -p pulsar-data
  chown -R 10000:10000 pulsar-data

  步骤二：生成 Secret Key 和 Token

  # 生成密钥
  docker run --rm -v $(pwd)/pulsar-data:/pulsar/data apachepulsar/pulsar:4.1.3 \
    bin/pulsar tokens create-secret-key --output /pulsar/data/secret.key

  # 生成 admin token（保存输出的 token 字符串）
  docker run --rm -v $(pwd)/pulsar-data:/pulsar/data apachepulsar/pulsar:4.1.3 \
    bin/pulsar tokens create --secret-key /pulsar/data/secret.key --subject admin

  步骤三：docker-compose.yml

services:  
  pulsar-standalone:  
    image: apachepulsar/pulsar:4.1.3  
    container_name: pulsar-standalone  
    hostname: pulsar  
    command: >  
      bash -c "bin/apply-config-from-env.py conf/standalone.conf && exec bin/pulsar standalone"  
    network_mode: "host"  
    volumes:  
      - /opt/pulsar/data/standalone:/pulsar/data  
      - ./pulsar-data/secret.key:/pulsar/conf/secret.key  
    environment:  
      PULSAR_MEM: "-Xms512m -Xmx1g -XX:MaxDirectMemorySize=512m"  
      authenticationEnabled: "true"  
      authorizationEnabled: "true"  
      superUserRoles: "admin"  
      authenticationProviders: "org.apache.pulsar.broker.authentication.AuthenticationProviderToken"  
      tokenSecretKey: "REDACTED_REFERENCE_SECRET"  
      brokerClientAuthenticationPlugin: "org.apache.pulsar.client.impl.auth.AuthenticationToken"  
      brokerClientAuthenticationParameters: '{"token":"REDACTED_REFERENCE_SECRET"}'

  步骤四：启动

  docker compose up -d

  步骤五：验证

  # 用 token 列出 tenant
  TOKEN="REDACTED_REFERENCE_SECRET"

  curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/admin/v2/tenants


拿到 admin token 后的完整步骤

  1. 创建 namespace

  ADMIN_TOKEN="xxx"

  curl -X PUT -H "Authorization: Bearer $ADMIN_TOKEN" \
    http://localhost:8080/admin/v2/namespaces/public/ads

  2. 创建 topic

  curl -X PUT -H "Authorization: Bearer $ADMIN_TOKEN" \
    http://localhost:8080/admin/v2/persistent/public/ads/ad-operation

  3. 生成业务用户 token

  docker run --rm -v $(pwd)/pulsar-data:/pulsar/data apachepulsar/pulsar:4.1.3 \
    bin/pulsar tokens create --secret-key /pulsar/data/secret.key --subject ads

  4. 给业务用户授权

  curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    http://localhost:8080/admin/v2/namespaces/public/ads/permissions/ads \
    -d '["produce","consume"]'

  5. 客户端用业务 token 连接

  client = pulsar.Client(
      'pulsar://ip:6650',
      authentication=pulsar.AuthenticationToken('ads的token')
  )
