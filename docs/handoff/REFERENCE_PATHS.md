# 历史参考代码本地路径导航

从仓库根目录的 [HANDOFF.md](../../HANDOFF.md) 进入本页。以下展示的路径均以克隆后的 **drmovira 仓库根目录** 为基准，不依赖盘符、旧机器目录或原仓库访问权限。链接可在 GitHub 或本地 Markdown 阅读器中打开，Codex 可直接按路径读取。

| 历史项目 | 仓库内目录 | 主要用途 |
| --- | --- | --- |
| 前端 | [reference-projects/ai-ad-platform-vben/](../../reference-projects/ai-ad-platform-vben/) | 投放管理页面、接口消费者、领域逻辑 |
| Java 后端 | [reference-projects/adpulse-power-system/](../../reference-projects/adpulse-power-system/) | 历史业务服务与系统权限调用链 |
| Python 后端 | [reference-projects/backend/](../../reference-projects/backend/) | 历史接口、服务、模型与数据库逻辑 |
| 调度程序 | [reference-projects/schedulers/](../../reference-projects/schedulers/) | 广告配置、操作、同步及素材任务 |

## 按目录查代码

### ai-ad-platform-vben

- 业务页面：[reference-projects/ai-ad-platform-vben/plat/src/views/](../../reference-projects/ai-ad-platform-vben/plat/src/views/)
- 接口调用：[reference-projects/ai-ad-platform-vben/plat/src/api/](../../reference-projects/ai-ad-platform-vben/plat/src/api/)
- 领域逻辑：[reference-projects/ai-ad-platform-vben/plat/src/domain/](../../reference-projects/ai-ad-platform-vben/plat/src/domain/)
- 路由：[reference-projects/ai-ad-platform-vben/plat/src/router/](../../reference-projects/ai-ad-platform-vben/plat/src/router/)

### adpulse-power-system

- main 业务源码：[reference-projects/adpulse-power-system/adpulse-main/src/main/java/](../../reference-projects/adpulse-power-system/adpulse-main/src/main/java/)
- system 系统源码：[reference-projects/adpulse-power-system/adpulse-system/src/main/java/](../../reference-projects/adpulse-power-system/adpulse-system/src/main/java/)
- 公共模块：[reference-projects/adpulse-power-system/adpulse-common/](../../reference-projects/adpulse-power-system/adpulse-common/)
- 历史设计文档：[reference-projects/adpulse-power-system/docs/](../../reference-projects/adpulse-power-system/docs/)

### backend

- 接口：[reference-projects/backend/app/api/](../../reference-projects/backend/app/api/)
- 业务服务：[reference-projects/backend/app/services/](../../reference-projects/backend/app/services/)
- 数据库访问：[reference-projects/backend/app/db/](../../reference-projects/backend/app/db/)
- 模型类型：[reference-projects/backend/app/model_type_defs/](../../reference-projects/backend/app/model_type_defs/)
- 表结构资料：[reference-projects/backend/table/](../../reference-projects/backend/table/)
- 历史测试：[reference-projects/backend/tests/](../../reference-projects/backend/tests/)

### schedulers

- 广告配置任务：[reference-projects/schedulers/tasks/ad_config/](../../reference-projects/schedulers/tasks/ad_config/)
- 广告操作任务：[reference-projects/schedulers/tasks/ad_operation/](../../reference-projects/schedulers/tasks/ad_operation/)
- 新版操作任务：[reference-projects/schedulers/tasks/ad_operation_new/](../../reference-projects/schedulers/tasks/ad_operation_new/)
- 新版同步任务：[reference-projects/schedulers/tasks/ad_sync_new/](../../reference-projects/schedulers/tasks/ad_sync_new/)
- BM 同步任务：[reference-projects/schedulers/tasks/fb_business_sync/](../../reference-projects/schedulers/tasks/fb_business_sync/)
- 素材推送任务：[reference-projects/schedulers/tasks/fb_material_push/](../../reference-projects/schedulers/tasks/fb_material_push/)
- 数据库访问：[reference-projects/schedulers/db/](../../reference-projects/schedulers/db/)
- 模型类型：[reference-projects/schedulers/model_type_defs/](../../reference-projects/schedulers/model_type_defs/)

## 使用边界及机器迁移

先从 [原需求包](../../data/ORBIT_Codex开发PRD/) 确认需求，再只读查对应参考代码。当前 ORBIT 实现位于 [orbit-web/](../../orbit-web/) 和 [orbit-server/python/](../../orbit-server/python/)，不能把历史项目当作当前启动入口。

[REFERENCE_SOURCES.json](REFERENCE_SOURCES.json) 的 `local_path` 和 `entry_points` 是上述仓库内路径；`previous_machine_path` 仅作来源记录，不能据此找本地代码。[快照说明](../../reference-projects/README.md) 和 [逐文件来源清单](../../reference-projects/SNAPSHOT_MANIFEST.json) 记录固定提交、排除项和脱敏。快照源码与原文中的绝对路径不作批量改写，以保留来源；接续开发按本页导航。

运行配置与参考源码分开处理：当前预览加载器仍有旧机器的私有配置路径限制，具体迁移步骤见 [HANDOFF 第5节](../../HANDOFF.md#5-新机环境与验证)。本次只调整文档导航，没有改变加载器，也没有附带私有配置。不要将 `reference-projects/` 当作秘密配置来源。
