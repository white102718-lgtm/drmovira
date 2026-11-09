# AdPulse Server

AdPulse 后端微服务聚合工程。系统管理服务提供有状态 JWT 登录、用户、角色、部门、菜单和 IP 白名单管理；主业务服务承载后续业务接口。

## 模块结构

```text
adpulse-server/
├── adpulse-common/   # 统一响应、JWT、Redis权威会话与认证过滤器
├── adpulse-system/   # 登录、MFA和系统管理服务，默认端口8080
└── adpulse-main/     # 主业务服务，默认端口8081
```

两个服务是独立进程，共用同一个 MySQL 数据库、Redis 实例、JWT 密钥与签发方。`system` 负责签发令牌；两个服务都会实时检查 Redis 会话和数据库用户/IP状态。当前不引入注册中心，也不包含服务间远程调用。1

## 环境

- JDK 21
- Maven 3.9+
- MySQL 8.0+
- Redis 7+

## 服务器目录规划

生产服务器统一使用以下目录：

```text
/opt/docker/
├── docker-compose.yml
├── .env
├── mysql/
│   ├── conf.d/
│   ├── data/
│   └── logs/
├── redis/
│   ├── conf/
│   ├── data/
│   └── logs/
└── java/system/
    ├── Dockerfile
    ├── .dockerignore
    ├── adpulse-system-server.jar
    ├── conf/application.env
    └── logs/
```

`docker-compose.yml` 只管理MySQL和Redis，使用上述绝对路径挂载。Java服务使用独立Docker容器运行，不加入Compose，生产日志默认写入 `/opt/docker/java/system/logs/adpulse-system-server.log`。

## 首次启动

### 启动 MySQL 和 Redis

在项目目录复制环境变量模板并修改所有密码，然后将Compose文件部署到 `/opt/docker`：

```bash
sudo mkdir -p /opt/docker/mysql/{conf.d,data,logs}
sudo mkdir -p /opt/docker/redis/{conf,data,logs}
sudo mkdir -p /opt/docker/java/system/{conf,logs,files}
sudo cp deploy/mysql/conf.d/adpulse.cnf /opt/docker/mysql/conf.d/
sudo cp deploy/redis/conf/redis.conf /opt/docker/redis/conf/
sudo cp docker-compose.yml .env.example /opt/docker/
cd /opt/docker
sudo mv .env.example .env
# 修改 .env 中的密码后执行
docker compose up -d
```

Compose 使用宿主机路径挂载：

```text
/opt/docker/mysql/conf.d -> MySQL配置
/opt/docker/mysql/data   -> MySQL数据
/opt/docker/mysql/logs   -> MySQL日志
/opt/docker/redis/conf   -> Redis配置
/opt/docker/redis/data   -> Redis数据
/opt/docker/redis/logs   -> Redis日志
```

MySQL 和 Redis 都监听 `0.0.0.0`，并通过宿主机的 `3306`、`6379` 端口提供远程连接。生产服务器必须通过安全组限制来源IP，并使用高强度密码。MySQL远程业务连接使用 `.env` 中的 `MYSQL_USER`，日常应用不要使用root账号。

首次启动前需要确保 MySQL、Redis 的数据和日志目录允许对应容器用户写入。

### 启动应用

先创建空数据库：

```sql
CREATE DATABASE adpulse_system
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

应用不集成 Flyway，也不会在启动时自动创建或升级表结构。首次部署必须按照版本号顺序手工执行数据库脚本：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V1__create_system_management_tables.sql
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V2__seed_system_permissions.sql
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V3__add_mfa_login_state.sql
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V4__drop_legacy_mfa_enabled.sql
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V5__create_login_log.sql
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V6__create_operation_log.sql
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V7__create_dictionary_tables.sql
```

已经执行过的版本不要重复执行。已完成 V1、V2、V3 的现有数据库只需执行 V4。V4 会删除认证逻辑不再使用的 `mfa_enabled` 字段，执行前检查、SQL 内容和执行后验证见 `docs/DATABASE_MANUAL_UPGRADE.md`。

以后新增数据库变更时，仍在该目录增加带版本号的 SQL，由部署人员审核后手工执行，再启动新版应用。

V5 创建登录审计表和 `system:login-log:list` 权限。执行 V5 后，管理员需要重新登录以刷新 Redis 中的权限快照。登录日志接口说明见 `docs/LOGIN_LOG_API.md`。

V6 创建操作审计表和 `system:operation-log:list` 权限。必须先执行 V6 再部署包含操作日志的 Java 服务；执行后管理员需要重新登录。操作日志接口说明见 `docs/OPERATION_LOG_API.md`。

V7 创建字典类型、字典项和 `system:dictionary:list` 权限，并初始化 `AD_MEDIA` 投放媒体字典。必须先执行 V7 再部署包含字典接口的 Java 服务；执行后管理员需要重新登录。接口说明见 `docs/DICTIONARY_API.md`。

V12 创建媒介资产回收单和 `media:resource:return:manage` 权限。必须先按顺序执行 V9、V11，再执行 V12 并部署回收接口；执行后管理员需要重新登录。接口与升级说明见 `docs/ASSET_RETURN_API.md`。

设置环境变量后启动：

```powershell
$env:DB_URL='jdbc:mysql://127.0.0.1:3306/adpulse_system?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai'
$env:DB_USERNAME='root'
$env:DB_PASSWORD='REDACTED_REFERENCE_SECRET'
$env:REDIS_HOST='127.0.0.1'
$env:JWT_SECRET='REDACTED_REFERENCE_SECRET'
$env:SPRING_PROFILES_ACTIVE='test'
$env:BOOTSTRAP_ADMIN_ENABLED='true'
$env:BOOTSTRAP_ADMIN_PASSWORD='REDACTED_REFERENCE_SECRET'
mvn -pl adpulse-system -am spring-boot:run
```

另开终端并使用相同的 `DB_*`、`REDIS_*`、`JWT_SECRET` 环境变量启动主业务服务：

```powershell
mvn -pl adpulse-main -am spring-boot:run
```

主业务服务的受保护验证入口为 `GET http://127.0.0.1:8081/api/main/home`，直接携带 system 登录签发的 Bearer Token。

首次空库启动时可以启用管理员引导。创建成功后立即关闭：

```powershell
$env:BOOTSTRAP_ADMIN_ENABLED='false'
```

默认接口根路径：`http://127.0.0.1:8080/api`。

当前前后端联调阶段全局允许任意来源、HTTP方法和请求头跨域访问，跨域请求不携带Cookie凭证。该配置只放开浏览器同源限制，不会绕过JWT、Redis会话、IP策略和接口权限。正式公网生产环境建议改为明确的前端域名白名单。

## 测试环境接口文档

测试环境启用了Knife4j，供前端查看和调试接口：

```text
http://127.0.0.1:8080/api/doc.html
```

OpenAPI JSON：

```text
http://127.0.0.1:8080/api/v3/api-docs
```

除登录接口外，受保护接口需要先调用`POST /auth/login`取得JWT，然后点击Knife4j页面的“Authorize”并填入JWT。页面会自动添加`Bearer`前缀。

Knife4j UI和OpenAPI端点只在`test` profile可用，`prod` profile会显式关闭并由Spring Security拒绝匿名访问。项目关闭了Knife4j增强扩展，以兼容Spring Boot 3.5所需的新版springdoc；接口浏览、JWT调试和OpenAPI导出不受影响。

## 环境配置

服务配置分别位于 `adpulse-system/src/main/resources/application.yml` 和 `adpulse-main/src/main/resources/application.yml`。

- 测试环境：`SPRING_PROFILES_ACTIVE=test`
- 生产环境：`SPRING_PROFILES_ACTIVE=prod`

生产环境不提供数据库、Redis和JWT密钥默认值，必须设置：

```text
DB_URL
DB_USERNAME
DB_PASSWORD
REDIS_HOST
REDIS_PASSWORD
JWT_SECRET
MFA_ENCRYPTION_KEY
MPOWER_FEISHU_APP_ID
MPOWER_FEISHU_APP_SECRET
```

`MFA_ENCRYPTION_KEY` 是Base64编码的32字节AES密钥，可通过 `openssl rand -base64 32` 生成。该密钥必须稳定保存，更换后已有MFA绑定将无法解密。

`MPOWER_FEISHU_APP_ID` 和 `MPOWER_FEISHU_APP_SECRET` 是系统通知使用的 Mpower 飞书机器人凭据。测试与生产共用机器人时，两套环境应分别通过私有环境文件注入相同值，不得将凭据写入仓库。

生产环境使用独立Docker容器部署，不加入 `docker-compose.yml`：

```bash
mvn clean package
sudo cp adpulse-system/target/adpulse-system-server-0.1.0-SNAPSHOT.jar \
  /opt/docker/java/system/adpulse-system-server.jar
sudo cp deploy/system/Dockerfile deploy/system/.dockerignore \
  /opt/docker/java/system/
sudo cp deploy/system/conf/application.env.example \
  /opt/docker/java/system/conf/application.env
# 修改application.env中的生产密码、密钥和飞书机器人凭据
sudo chmod 640 /opt/docker/java/system/conf/application.env

cd /opt/docker/java/system
docker build -t adpulse-system-server:0.1.0 .
docker run -d \
  --name adpulse-system-server \
  --restart unless-stopped \
  --network docker_default \
  --env-file /opt/docker/java/system/conf/application.env \
  -p 0.0.0.0:8080:8080 \
  -v /opt/docker/java/system/logs:/opt/docker/java/system/logs \
  -v /opt/docker/java/system/files:/opt/docker/java/system/files \
  adpulse-system-server:0.1.0
```

Java容器独立运行，但加入Compose创建的 `docker_default` 网络，通过容器名称访问MySQL和Redis。若Compose项目名称或启动目录不同，应先检查MySQL容器所在网络，并替换 `--network` 参数。`JAVA_TOOL_OPTIONS` 默认设置初始堆为512MB、最大堆为2GB；这里只约束JVM堆内存，不限制Docker容器总内存。

查看运行状态和日志：

```bash
docker ps --filter name=adpulse-system-server
docker logs --tail=100 -f adpulse-system-server
```

## 常用命令

```powershell
mvn spotless:apply
mvn test
mvn verify
```

## 认证方式

所有成功响应的业务码均为 `200`，错误码统一使用三位数并按展示策略分段，详见 [API 响应码规范](docs/API_RESPONSE_CODE.md) 和 [前端统一接口响应处理规范](docs/FRONTEND_API_RESPONSE_INTEGRATION.md)。密码登录：

```http
POST /api/auth/login
Content-Type: application/json

{
  "identifier": "admin",
  "password": "REDACTED_REFERENCE_SECRET"
}
```

登录响应通过 `loginStatus` 指示下一步：

- `SUCCESS`：认证完成，返回JWT。
- `MFA_BIND_REQUIRED`：使用返回的 `otpAuthUri` 绑定验证器，再调用 `POST /api/auth/mfa/bind`。
- `MFA_VERIFY_REQUIRED`：调用 `POST /api/auth/mfa/verify` 验证六位动态码。

MFA绑定和验证请求：

```json
{
  "challengeToken": "REDACTED_REFERENCE_SECRET",
  "totpCode": "123456"
}
```

其他请求携带：

```http
Authorization: Bearer <access-token>
```

JWT 和 Redis 会话必须同时有效。删除 Redis 会话后，尚未过期的 JWT 也会立即失效。

登录完成后，前端通过 `GET /api/menus` 获取当前用户有效角色对应的动态路由菜单。该接口不需要菜单管理权限，返回格式和对接说明见 `docs/CURRENT_USER_MENU_API.md`。

完整MFA交互和密钥管理说明见 `docs/MFA_AUTH_FLOW.md`。

## 项目约束

实施流程见 `docs/IMPLEMENTATION_PLAN.md`。后续自动化修改必须先读取根目录 `AGENTS.md` 和 `.codex/skills/adpulse-system-backend/SKILL.md`。
