# Project Instructions

## Auto Skill Creation

When working on tasks, proactively identify opportunities to create reusable skills (slash commands). If a workflow is repetitive, multi-step, or likely to be reused, create a skill file automatically:

- Always create at project level: `.claude/skills/<name>/SKILL.md`
- Do NOT create global skills at `~/.claude/skills/`

Always inform the user what skill was created and why.

## Working Principles

1. **No guessing — speak from evidence.** If you don't see proof, say so. Do not dress up "the most likely explanation" or "it might be because" as a conclusion. Seeing field X = Y does not mean Y is the root cause — verify first.
2. **No over-engineering.** If the requirement is to print one log line, change one line. Do not add dataclasses, properties, caches, or abstractions on the side. Build the minimum that works; expand only when someone asks.
3. **No essay comments — 注释言简意赅,不写小论文。** 不要把推理过程、trade-off、对照旧代码、引用别处文件/行号成段塞进代码注释。代码注释只留"未来读这行代码的人需要的最少信息":非显然的约束、隐藏的不变量、绕开具体 bug 的 workaround。机制解释、背景对照、trade-off 罗列 → 写在 PR 描述或回复里,不要留在代码里。删掉不会让读者困惑的注释,就不要写。
4. **Converge new cases onto the nearest existing path — 加新分支先找语义最近的兄弟路径。** 给功能加新 case(多一种状态 / 入口 / 触发方式)时,先找系统里语义最接近的已有实现,让新 case 汇进去——产出同样的数据,走同样的渲染 / 处理 / 跳转;不要顺着"当前调用入口现在恰好是什么机制"给它单独配一条平行实现,导致同一件事两套代码。判断"兄弟":在用户眼里新 case 跟哪个已有功能是同一件事,就跟它走同一条路。
