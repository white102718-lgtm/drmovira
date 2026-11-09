---
name: which-service-to-restart
description: Given a git commit / range / working diff, figure out which docker services under deploy/ need to be restarted. Use when the user asks "改了这些要重启哪个服务 / which service to restart / 哪个服务要重启".
---

# 排查哪个服务要重启

本项目多个 docker 服务共享同一份代码，每个服务由 `deploy/<name>/Dockerfile` 的 `CMD` 指定入口模块。判断一个改动是否影响某服务，就是判断该服务的入口模块是否（直接或间接）加载了改动过的符号。

## 步骤

1. **找出改动的文件**
   - 指定 commit: `git show --stat <sha>`
   - 最近 N 个: `git diff HEAD~N HEAD --stat`
   - 工作区: `git status` + `git diff --stat`

2. **列出所有服务及其入口**（运行一次即可缓存）
   ```bash
   for d in deploy/*/; do
     echo "=== $d ==="
     grep -E "^CMD|^ENTRYPOINT" "$d/Dockerfile" 2>/dev/null
   done
   ```
   当前已知的常驻服务：
   | 服务 (deploy 目录) | 入口模块 |
   |---|---|
   | `ad_materials_fetch_worker` | `tasks.ad_materials.ad_materials_fetch_worker` / `ad_creative_scrape_worker`(见 deploy/ad_materials_fetch_worker) |
   | `ad_operation` | `tasks.ad_operation.op_consumer` |
   | `ad_operation_new` | `tasks.ad_operation_new.op_consumer`（新系统，与 `ad_operation` 代码独立，改一边不影响另一边） |
   | `ad_sync_c` | `tasks.ad_sync.consumer` |
   | `check_ad_status` | `tasks.check_ad_status.tg_callback_worker` |
   | `fb_account_consumer` | `tasks.ad_sync.fb_account_consumer` |
   | `fb_business_consumer` | `tasks.fb_business_sync.fb_business_consumer` |
   | `schduler_main` | `tasks.main` （APScheduler 调度器，注册大量 job） |

3. **对每个改动文件分类**
   - `scripts/*.sql` / `scripts/*.py` 下只改了 `if __name__ == "__main__"` 块 → **不影响常驻服务**
   - `tasks/...` 或 `utils/...` 的函数/类定义被改 → 下一步查 import 链
   - `deploy/<svc>/Dockerfile` 或 `docker-compose.yml` → **那个服务必须 rebuild+重启**
   - `conf/`, `env_vault/`, 依赖（`requirements.txt`）改了 → 使用它的服务都要重启

4. **对每个改动的符号/模块追 import 链**
   - 先 grep 直接引用: `Grep pattern="<symbol>|<module>"`
   - **关键：`schduler_main` 最容易被漏**。它在 `tasks/main.py` 中集中注册所有定时 job，很多工具函数都是通过它被调度。凡是被改到的函数如果在 `tasks/main.py` 中出现（直接 import 或通过某个 wrapper），就需要重启 `schduler_main`。
   - 对于共享工具（`utils/*.py`）：找出**被改函数/类**的所有调用方，而不是整个文件的 importer。只要常驻服务链路上**调用了改动过的符号**才需要重启，否则不用。

5. **输出结论表**
   列出：每个改动 → 影响的服务（或"仅手动脚本 / 仅建表 SQL / 无影响"）。
   
   重启命令示例（在对应 deploy 目录）：
   ```bash
   cd deploy/<service>
   docker compose up -d --build
   ```

## 易错点

- 只看文件级的 importer 会误报。一定要追到**具体符号**。
- 只搜 `tasks/` 子目录会漏掉 `tasks/main.py`。搜索时默认从仓库根开始。
- `__main__` 块里的改动（日期参数、batch size 等）**不影响** 以 module 方式 import 该文件的服务。
- Dockerfile `CMD` 有时写错扩展名（如 `tg_callback_worker.py` 作为模块名），但仍是 `python -m` 形式 —— 按实际入口文件判断。
