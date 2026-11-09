# ad-mpower 历史项目只读源码

此目录让接手同事无需原仓库权限即可查阅历史业务实现。**只供参考，不是ORBIT运行依赖，不执行其中启动、部署或广告操作。** ORBIT仍使用Vue3/Element Plus、Python/RuoYi-FastAPI、MySQL8和Redis；这里的Vben/Ant Design、Java实现不能覆盖新项目的技术决定。

| 目录 | 已提交版本 | 文件数 |
| --- | --- | ---: |
| [ai-ad-platform-vben](ai-ad-platform-vben/) | `1b2b48d86cb2722c0194a610a363aced93802f53` | 1843 |
| [adpulse-power-system](adpulse-power-system/) | `325bb98d5828fcde08460fa13bdf55110755a0ff` | 802 |
| [backend](backend/) | `0565d8a342eb64b044d190fb5c3dc48636d9c269` | 179 |
| [schedulers](schedulers/) | `4ed5d58a08321e0c0701a74905df0e17fa02edac` | 193 |

这四份快照由旧机已缓存的`origin/devhs`提交对象导出，导出时各项目HEAD与其上游跟踪提交相同、未推送提交数为0；不是对本地目录直接复制，也不声称是原远端此后的最新版本。

- 仅导出Git已提交文件，没有本地未提交/未跟踪文件、`.git`历史或原仓库认证信息。
- 不含`node_modules`、虚拟环境、编译产物、运行日志、缓存、数据库或表格导出。
- 环境与密钥文件排除；识别出的凭据字面量替换为`REDACTED_REFERENCE_SECRET`。因此不是可直接启动的生产副本，脱敏处不能被理解为真实默认配置。
- 原项目工作区未改动。导出文件的原始/现有SHA-256、脱敏次数及排除路径见[SNAPSHOT_MANIFEST.json](SNAPSHOT_MANIFEST.json)。校验值用于来源核对，不包含原凭据内容。
- 许可证、业务源码、已提交的测试与设计文档保留；本地路径和原项目AGENTS/部署说明仅描述历史项目，不授权操作任何外部环境。
- 使用方式：先按ORBIT原合同确定行为，不清晰时只读查这里相应实现；不要把参考代码、框架或数据库凭据直接作为ORBIT当前实现。

例如前端业务入口位于`ai-ad-platform-vben/plat/src/`，Java历史业务位于`adpulse-power-system/adpulse-system/`与`adpulse-main/`，Python历史接口位于`backend/app/`，调度任务位于`schedulers/tasks/`。具体文件以快照实际树为准。
