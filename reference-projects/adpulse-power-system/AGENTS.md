# AdPulse System Server Agent Rules

Before modifying this repository, read `.codex/skills/adpulse-system-backend/SKILL.md`. Read its referenced architecture or database document when the change touches that area.

## 系统技术框架

- 运行时与构建：Java 21、Maven 多模块、Spring Boot 3.5。
- Web 与接口：Spring MVC、Jakarta Validation、统一 `ApiResponse` 业务响应。
- 安全与会话：Spring Security、JJWT、Redis；JWT 仅作为会话凭证，Redis 会话为最终依据。
- 业务数据库：MySQL 8，统一通过 MyBatis + Mapper XML 访问；业务代码禁止新增 `JdbcTemplate`、`NamedParameterJdbcTemplate`、`DriverManager` 或手写 JDBC 连接。
- 分析数据库：Doris 连接位于 `adpulse-main/.../channel/doris/**`，现有 `NamedParameterJdbcTemplate` 属于明确例外，除 Doris 专项需求外不得修改或迁移。
- 接口文档：Springdoc OpenAPI + Knife4j。
- 测试与质量：JUnit 5、Mockito、Spotless、Google Java Format。
- 数据库脚本：由人工审核并在部署前执行，应用启动时不自动迁移表结构。

## 分层与数据访问要求

- Controller 只负责 HTTP 参数适配与响应，不直接写 SQL，也不持有数据库访问组件。
- Service 负责业务规则、权限校验和事务边界；跨表写入必须在 Service 层使用事务保证一致性。
- Mapper 负责持久化，SQL 统一放在 `src/main/resources/mapper/**` 的 XML 中；动态条件使用 MyBatis 标签和命名参数，禁止拼接用户输入。
- 普通 CRUD 优先复用现有 Mapper；复杂查询建立语义清晰的 Mapper 方法和查询模型，避免以通用 Map 掩盖稳定领域结构。
- 新增数据访问代码前先确认是否为 Doris：仅 Doris 保留 JDBC 模式，其余数据库访问一律使用 MyBatis。

## 编码与可读性要求

- 公共类型、公共业务方法以及不直观的业务判断必须编写简洁中文 Javadoc 或中文注释，重点解释业务意图、约束和边界条件，不重复描述语法。
- 变量、类和方法使用准确的英文业务命名；方法保持单一职责，复杂流程拆分为可读的私有方法，避免超长方法和重复代码。
- 使用构造器注入，避免字段注入；优先使用明确类型，只有动态表单等结构确实不稳定时才使用 `Map<String, Object>`。
- 保持统一代码格式：Java 修改后执行 Spotless/Google Java Format，Mapper XML 保持清晰缩进，长 SQL 每行只放一组字段或条件。
- 注释、日志和异常信息应清楚且可维护；不得保留乱码注释，不写无意义注释，不吞异常，不在失败后返回成功。
- 修改业务逻辑时同步新增或更新测试，覆盖正常路径、权限/状态冲突、空值和关键边界条件。

Non-negotiable rules:

- Do not add database foreign keys. Enforce references in transactional services.
- Use `deleted_at = 0` for active rows and Unix epoch milliseconds for soft-deleted rows.
- Keep controllers thin and put authorization and business invariants in services.
- Treat JWT as a session credential; every authenticated request must also resolve an active Redis session.
- Add Chinese Javadoc to public types and non-obvious public methods.
- Format Java with Spotless/Google Java Format and keep mapper XML consistently indented.
- Never persist or log plaintext passwords, JWT secrets, MFA secrets, or full tokens.

## Doris Development Metadata

The following Doris metadata was verified against the development environment on 2026-08-24. Do not reconnect merely to rediscover these names:

- MySQL JDBC Catalog: `mysql_adpulse_system`
- MySQL database: `adpulse_system`
- Channel account external table: `mysql_adpulse_system.adpulse_system.media_channel_account`
- Doris internal Catalog: `internal`
- Doris spend database: `ad`
- Daily spend table: `internal.ad.ad_daily_detail`
- Spend join key: `media_channel_account.account_id = ad_daily_detail.account_id`
- Spend date column: `ad_daily_detail.date`
- Account-level rows: `ad_daily_detail.level = 'account'`
- Spend amount column: `ad_daily_detail.amount_spent`, denominated in USD

Environment-specific names are configured with `DORIS_MYSQL_CATALOG`, `DORIS_MYSQL_DATABASE`, `DORIS_SPEND_CATALOG`, and `DORIS_SPEND_DATABASE`. Keep Doris isolated from Spring's primary `DataSource`; MyBatis business queries must continue using MySQL, while Doris access goes through the private `DorisJdbcClient`.
