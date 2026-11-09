# AdPulse System Server 实现流程

## 1. 建设目标

新建独立后端项目 `adpulse-system-server`，实现系统管理领域：认证、用户、角色、部门和菜单管理。项目不读取、不依赖现有 `adpulse-power-server`。

技术栈：

- Java 21
- Spring Boot 3.5.x
- Spring Security 6
- MyBatis 3
- MySQL 8
- Redis
- JWT（有状态会话）
- 手工执行的 MySQL 初始化和升级脚本
- Maven

## 2. 核心约束

1. 数据库不声明外键，Service 层通过查询、事务和唯一索引保证引用完整性。
2. 所有业务表使用 `BIGINT UNSIGNED` 主键；HTTP JSON 中的 ID 使用字符串，避免 JavaScript 精度丢失。
3. 所有业务表使用 `deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0`；`0` 表示有效，其他值为 Unix 毫秒时间戳。
4. 业务唯一索引必须包含 `deleted_at`，允许软删除后重新使用业务标识。
5. Mapper 接口使用 Java 注解表达简单 SQL，复杂 SQL 必须放在格式化后的 XML 中。本项目系统管理查询统一优先使用 XML，避免 SQL 分散。
6. Controller 只负责协议适配；业务校验、事务与引用完整性放在 Service 层。
7. 所有公共类型、Controller、Service 及非显然业务方法编写中文 Javadoc；注释说明业务原因，不复述代码。
8. JWT 仅作为会话凭证。登录成功后在 Redis 保存服务端会话；登出、禁用用户、修改密码后可立即撤销会话。

## 3. 分阶段实施

### 阶段一：工程骨架与约束

- 创建 Maven/Spring Boot 工程。
- 固化包结构、Checkstyle 和 Spotless 格式化规则。
- 创建根目录 `AGENTS.md`。
- 创建项目专用 Codex skill，并将数据库和架构细节放入 references。
- 配置本地开发环境示例，不提交真实密码。

验收标准：工程目录完整，约束文件可被后续会话发现。

### 阶段二：数据库与公共基础设施

- 按版本顺序手工执行 SQL，创建部门、用户、角色、菜单及关联表；应用不自动修改数据库结构。
- 实现统一响应、分页、异常处理和错误码。
- 实现毫秒时间戳软删除约定。
- 配置 MyBatis 下划线转驼峰、XML Mapper 路径及分页参数。

验收标准：迁移脚本可重复审查，表结构与最终设计一致。

### 阶段三：认证与会话

- 实现手机号或用户名登录。
- 使用 BCrypt 校验密码。
- 签发短期 JWT，JWT 中只保存会话 ID、用户 ID 和必要声明。
- Redis 保存会话状态、权限快照和到期时间。
- 每次请求校验 JWT 签名、Redis 会话、用户状态。
- 实现登录、登出、当前用户、刷新会话接口。
- 实现 IP 模式：关闭、全部允许、白名单。

验收标准：删除 Redis 会话后 JWT 立即失效。

### 阶段四：部门和菜单

- 部门树查询、详情、新增、修改、移动、停用和软删除。
- 防止部门移动到自身子树。
- 菜单树查询、详情、新增、修改、排序、停用和软删除。
- 菜单支持目录、菜单、按钮三级权限资源。

验收标准：树结构稳定，删除前完成引用检查。

### 阶段五：角色和用户

- 角色分页、详情、新增、修改、停用和软删除。
- 配置角色菜单权限。
- 用户分页、详情、新增、修改、停用和软删除。
- 配置用户角色、主部门和部门数据范围。
- 重置密码、重置 MFA、撤销用户会话。

验收标准：所有关联写入使用事务，禁止产生有效孤儿关系。

### 阶段六：质量验证

- 为认证、部门移动、软删除唯一性和权限计算编写测试。
- 执行 Maven 测试、Spotless 和 Checkstyle。
- 检查 Mapper XML 格式、Javadoc 和敏感配置。
- 输出启动说明和接口概览。

验收标准：在具备 Java 21 和 Maven 的环境中可通过全部质量门禁。

## 4. 包结构

```text
com.adpulse.system
├── SystemServerApplication
├── common
│   ├── api
│   ├── exception
│   ├── model
│   └── security
├── config
├── auth
├── department
├── menu
├── role
└── user
```

每个业务模块按职责拆分：

```text
controller / service / mapper / model / dto
```

## 5. 有状态 JWT 设计

1. 用户登录成功后生成随机 `sessionId`。
2. Redis 写入 `adpulse:session:{sessionId}`，内容包含用户ID、权限版本、登录IP和创建时间。
3. JWT 保存 `sessionId`、用户ID、签发时间和过期时间并完成签名。
4. 请求过滤器先验证 JWT，再读取 Redis 会话；任一步失败均拒绝请求。
5. 登出删除当前 Redis 会话。
6. 用户停用、删除、修改密码或重置安全信息时，撤销该用户全部会话。

## 6. 本地运行依赖

- JDK 21
- Maven 3.9+
- MySQL 8.0+
- Redis 7+

数据库密码、Redis密码和JWT密钥通过环境变量传入，不写入仓库。
