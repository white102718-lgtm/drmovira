# ORBIT

ORBIT 广告投放管理后台的前后端合并仓库。

**接手开发先读：[开发交接与Codex接续](HANDOFF.md)。** 产品原始资料完整保存在`data/`，可执行`python tools/verify_handoff.py`校验本次交接文件。

ad-mpower四个历史项目的Git已提交源码已附在[reference-projects/](reference-projects/README.md)，仅供只读参考，不含node_modules、本地改动或真实凭据，无需原仓库权限即可查阅。接续时按[参考代码本地路径导航](docs/handoff/REFERENCE_PATHS.md)定位具体目录。

| 目录 | 内容 |
| --- | --- |
| `orbit-web/` | Vue 3、Element Plus 前端，保留若依布局及原菜单 |
| `orbit-server/python/orbit_api/` | Python 业务后端 |
| `orbit-server/python/ruoyi_fastapi/` | RuoYi-FastAPI 框架底座及原许可证 |
| `orbit-server/python/orbit_api/migrations/` | Python 版本数据库迁移 |
| `orbit-server/python/tests/` | Python 测试 |
| `orbit-server/tools/` | 本地启动、数据库及验收工具 |
| `orbit-server/docs/orbit/` | 实施文档、逐项进度及具名验收证据 |

后端使用 Python、MySQL 8 和 Redis。Java 历史源码与旧证据保留用于迁移核对，不是当前后端启动入口，也不计为 Python 版本验收通过。

## 本地开发

前端：进入 `orbit-web`，按项目要求使用 pnpm 安装依赖，再执行 `pnpm dev`。

后端：按 [后端说明](orbit-server/README.md) 安装 Python 依赖、准备独立 MySQL/Redis 和私有配置，再使用 `orbit-server/tools/start-orbit.ps1`。数据库初始化及升级需显式执行已审核迁移；上传仓库不会自动启动服务、部署或修改广告。

私有配置、API Token、数据库凭据、依赖目录、运行缓存和日志不随代码上传。当前本机配置加载约定见 [后端实施约定](orbit-server/AGENTS.md)，迁移到其他设备时须重新配置受控来源，不要将真实凭据提交到仓库。

## 当前开发状态

本次上传包含当前工作区代码，也包含明确仍在开发或尚未完整验收的功能；不能将代码已上传理解为产品全部完成。

- [完整实施方案](orbit-server/docs/orbit/IMPLEMENTATION_PLAN.md)
- [开发、测试、验收进度](orbit-server/docs/orbit/PROGRESS.md)
- [模块逻辑](orbit-server/docs/orbit/MODULE_LOGIC.md)
- [规则业务闭环与剩余缺口](orbit-server/docs/orbit/RULE_DEFINITION_BUSINESS_FLOW.md)
- [源码来源与逐文件 SHA-256 清单](SOURCE_MANIFEST.json)

原前后端目录名称保持不变，以保留现有工具中的相邻目录引用。上游来源及许可证分别保留于各目录。
