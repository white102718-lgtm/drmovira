# Project Instructions

## Working Process: Verify Before Acting

Do not execute edits based on口述 or assumption. Every change must go through **read → confirm → write**, in that order.

1. **Read the authoritative source first.** Before modifying anything, locate and read the file(s) that define the ground truth for what you're changing (schema files, type definitions, config files, the function being called, etc.). What the user said is a hint, not a spec.
2. **Confirm the specifics against what you read.** Exact name, exact type, exact signature, exact location. If something in the user's request doesn't match what you found, stop and ask — don't reconcile silently.
3. **Only then edit.** State briefly what you verified and are about to change, then do it.

When uncertain about where the authoritative source lives, search first (Grep/Glob) rather than guessing. If it genuinely isn't findable, ask the user — never fabricate.

This applies to every kind of change: SQL fields, function calls, config keys, file paths, import paths, API shapes. The failure mode to avoid is "the user said X, so I wrote X" without ever verifying X exists or is spelled that way.

## Auto Skill Creation

When working on tasks, proactively identify opportunities to create reusable skills (slash commands). If a workflow is repetitive, multi-step, or likely to be reused, create a skill file automatically:

- Always create at project level: `.claude/skills/<name>/SKILL.md`
- Do NOT create global skills at `~/.claude/skills/`

Always inform the user what skill was created and why.

## Working Principles

1. **No guessing — speak from evidence.** If you don't see proof, say so. Do not dress up "the most likely explanation" or "it might be because" as a conclusion. Seeing field X = Y does not mean Y is the root cause — verify first.

   **解释现象时的流程**:对"陈述事实"和"给原因"这两件事,默认只做第一件:
   - 看到 X=59 撞墙 → 只描述 "撞墙时 X=59",**不**断言 X 是原因。
   - 要给原因时,必须有 (a) 正例 (b) 反例,且 (c) 两者都来自本会话的数据,不要用外部推论。
   - 缺任一项时,可以说"可能是 X,需要继续排查",**不要说"是 X 导致的"**。
   - 外部文档 / 社区帖 / 训练知识只能作为"外部说法"引用,不能作为因果证明。
   - 新证据出现时直接撤回上一版结论,不要在错误结论上叠加修补。

2. **No over-engineering.** If the requirement is to print one log line, change one line. Do not add dataclasses, properties, caches, or abstractions on the side. Build the minimum that works; expand only when someone asks.

3. **No essay comments — 注释言简意赅,不写小论文。** 不要把推理过程、trade-off、对照旧代码、引用别处文件/行号成段塞进代码注释。代码注释只留"未来读这行代码的人需要的最少信息":非显然的约束、隐藏的不变量、绕开具体 bug 的 workaround。机制解释、背景对照、trade-off 罗列 → 写在 PR 描述或回复里,不要留在代码里。删掉不会让读者困惑的注释,就不要写。
4. **Converge new cases onto the nearest existing path — 加新分支先找语义最近的兄弟路径。** 给功能加新 case(多一种状态 / 入口 / 触发方式)时,先找系统里语义最接近的已有实现,让新 case 汇进去——产出同样的数据,走同样的渲染 / 处理 / 跳转;不要顺着"当前调用入口现在恰好是什么机制"给它单独配一条平行实现,导致同一件事两套代码。判断"兄弟":在用户眼里新 case 跟哪个已有功能是同一件事,就跟它走同一条路。
5. **Fix the disease, not the symptom — 碰到别扭点,先问"它是什么的症状",往上追一层再动手。** 干活途中遇到的任何摩擦——报错、绕路写法(如函数内 import 躲循环引用)、重复代码、不得不加的特判、奇怪的命名/参数——都默认是某个更深的设计、归属或假设错误的产物。不要只把眼前任务绕过去:先追问"什么样的上游错误会逼出这个现象",用证据确认病根,指出它 + 给出根上的最小修法,由用户决定修表面还是修根。只修表面时要明说"病根还在,在哪"。
