"""从不可修改的产品基线生成逐项进度；缺少实际证据时禁止勾选通过。"""

from __future__ import annotations

import argparse
import collections
import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "orbit"
BASELINE = DOCS / "baseline"
LEDGER = DOCS / "progress.json"
MODULES = {
    "global": "全局、若依基础与综合验收",
    "accounts": "广告账户管理",
    "launch": "自动化投放、模板与任务",
    "monitor": "广告投放数据与建议",
    "rules": "规则引擎与分析",
    "assets": "素材库与标签分类",
    "environments": "AdsPower监测与Agent",
    "channels": "渠道管理",
    "system": "系统管理与系统配置",
}
FIELD_MODULES = {
    "通用": "global", "账户": "accounts", "户商导入": "accounts",
    "投放": "launch", "投放渠道": "launch", "模板": "launch",
    "规则": "rules", "建议": "monitor", "渠道报表": "monitor",
    "素材": "assets", "标签分类": "assets", "环境": "environments",
    "渠道": "channels", "系统": "system", "所有权": "global",
    "主数据": "global", "分配": "launch", "反馈": "launch",
    "历史": "global", "权限": "global", "计划": "launch",
    "报表": "monitor", "手工操作": "monitor", "提醒": "monitor",
}
METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
LABELS = {
    "NOT_STARTED": "未开发", "IN_PROGRESS": "开发中", "DONE": "已开发",
    "NOT_RUN": "未运行", "RUNNING": "测试中", "PASS": "通过",
    "FAIL": "失败", "BLOCKED": "阻断",
}


def read_json(path: Path):
    """读取UTF-8合同；不依赖系统默认编码。"""
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    """用稳定hash发现原需求或业务规则变化，避免旧验收自动沿用。"""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def now() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def entry(item_id: str, kind: str, module: str, title: str, source: str, spec) -> dict:
    """新条目三个阶段均未完成；文档覆盖不能给业务状态加勾。"""
    return {
        "id": item_id, "kind": kind, "module": module, "title": title,
        "source": source, "spec": spec, "spec_sha256": digest(spec),
        "development": {"status": "NOT_STARTED", "evidence": []},
        "testing": {"status": "NOT_RUN", "evidence": []},
        "acceptance": {"status": "NOT_RUN", "evidence": []},
        "blocker": "", "notes": "",
    }


def module_for_path(path: str) -> str:
    """按活动路由归类，独立任务/模板动作仍归投放模块。"""
    resource = path.removeprefix("/api/v1/").split("/")[0]
    if resource in {"scope-snapshots", "attribution-corrections", "reference-catalogs"}:
        return "global"
    groups = {
        "accounts": {"accounts", "account-imports", "account-grants"},
        "launch": {"launch-plans", "launch-stats", "templates", "tasks", "allocations"},
        "monitor": {"metrics", "reports", "entities", "suggestions", "operations", "exports", "alerts", "manual-operations", "adoption-stats", "optimization-batches"},
        "rules": {"rules", "rule-hits", "analysis-jobs"},
        "assets": {"assets", "asset-uploads", "tags", "categories"},
        "environments": {"agents", "environments", "profiles", "profile-bindings", "reconciliation-cases", "capabilities", "agent-api", "environment-capabilities", "execution-agents"},
        "channels": {"channels"},
    }
    return next((module for module, prefixes in groups.items() if resource in prefixes), "system")


def refs_in(value):
    """递归枚举本地引用；只跟踪活动操作可达Schema，不复活退役模块。"""
    if isinstance(value, dict):
        if isinstance(value.get("$ref"), str):
            yield value["$ref"]
        for nested in value.values():
            yield from refs_in(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from refs_in(nested)


def expected_items() -> list[dict]:
    """完整提取FR、逻辑/界面条目、精确字段、HTTP操作及其可达字段。"""
    items = []
    for requirement in read_json(BASELINE / "requirements.json"):
        requirement = copy.deepcopy(requirement)
        if requirement["id"] == "FR-UI-01":
            requirement["user_override"] = "使用官方若依Vue3与原生Element Plus；保留layout和原菜单，不强制React/AntD或原型像素尺寸。业务信息、完整交互、可读性与响应式验收仍需通过。"
        elif requirement["id"] == "FR-GEN-01":
            requirement["user_override"] = "保留若依原菜单，新增ORBIT工作台及八业务模块；八模块白名单适用于ORBIT业务，不删除若依自带功能。"
        items.append(entry(requirement["id"], "requirement", requirement["module"],
                           "若依布局与Element Plus（用户覆盖原技术选型）" if requirement["id"] == "FR-UI-01" else requirement["title"],
                           "baseline/requirements.json", requirement))

    module = "global"
    for line in (DOCS / "MODULE_LOGIC.md").read_text(encoding="utf-8").splitlines():
        match = re.match(r"<!-- module:(\w+) -->", line)
        if match:
            module = match[1]
        if not re.match(r"\| (?:GEN|ACC|LCH|MON|RUL|AST|ENV|CHN|SYS|CFG|FLOW)-\d+ \|", line):
            continue
        item_id, surface, behavior, assertions = [value.strip() for value in line.strip("|").split("|")]
        items.append(entry(item_id, "behavior", module, f"{surface}：{behavior}",
                           "MODULE_LOGIC.md", {"surface": surface, "behavior": behavior, "assertions": assertions}))

    for filename, prefix in (("fields.json", "FIELD-B"), ("fields-extension.json", "FIELD-E")):
        for field in read_json(BASELINE / "contracts" / filename):
            module = FIELD_MODULES.get(field["module"], "global")
            item_id = f"{prefix}-{field['module']}.{field['key']}"
            items.append(entry(item_id, "field", module, f"{field['module']}.{field['key']}（{field.get('label', '扩展字段')}）",
                               f"baseline/contracts/{filename}", field))

    config_fields = DOCS / "extensions" / "configuration-fields.json"
    if not config_fields.exists() or not read_json(config_fields):
        raise ValueError("新增系统配置字段未导出，拒绝生成缺少该模块字段的台账")
    if config_fields.exists():
        for field in read_json(config_fields):
            items.append(entry(f"FIELD-CFG-{field['section']}.{field['key']}", "config_field", "system",
                               f"{field['section_label']}.{field['label']}", "extensions/configuration-fields.json", field))
    extension_contract = DOCS / "extensions" / "system-configurations.openapi.json"
    identity_extension = DOCS / "extensions" / "system-identity-fields.json"
    if identity_extension.exists():
        identity = read_json(identity_extension)
        for field_name, definition in identity["user_write_additions"].items():
            items.append(entry(f"FIELD-IDENTITY-UserWrite.{field_name}", "identity_field", "system",
                               f"UserWrite.{field_name}（正文补充）", "extensions/system-identity-fields.json",
                               {"schema": "UserWrite", "property": field_name, "definition": definition}))
        for field_name, definition in identity["user_read_additions"].items():
            items.append(entry(f"FIELD-IDENTITY-User.{field_name}", "identity_field", "system",
                               f"User.{field_name}（正文补充，只读）", "extensions/system-identity-fields.json",
                               {"schema": "User", "property": field_name, "readOnly": True,
                                "definition": definition, "implementation_status": "IN_PROGRESS"}))
    if extension_contract.exists():
        for path, path_item in read_json(extension_contract)["paths"].items():
            for method, operation in path_item.items():
                items.append(entry(f"API-CFG-{operation['operationId']}", "config_api", "system",
                                   f"{method.upper()} {path}", "extensions/system-configurations.openapi.json",
                                   {"path": path, "method": method.upper(), **operation}))

    for filename, prefix in (("team-capabilities.openapi.json", "TEAM"), ("role-capabilities.openapi.json", "ROLE"), ("user-capabilities.openapi.json", "USER")):
        directory_extension = DOCS / "extensions" / filename
        if not directory_extension.exists():
            continue
        definition = read_json(directory_extension)
        source = "extensions/" + filename
        for path, path_item in definition["paths"].items():
            for method, operation in path_item.items():
                items.append(entry(f"API-{prefix}-{operation['operationId']}", "directory_api", "system",
                                   f"{method.upper()} {path}", source,
                                   {"path": path, "method": method.upper(), **operation}))
        for name, schema in definition["components"]["schemas"].items():
            for prop, value in schema["properties"].items():
                items.append(entry(f"SCHEMA-{prefix}-{name}.{prop}", "identity_field", "system",
                                   f"{name}.{prop}（目录能力扩展）", source,
                                   {"schema": name, "property": prop, "definition": value}))

    contract = read_json(BASELINE / "contracts" / "openapi-current.json")
    menu_map = read_json(BASELINE / "contracts" / "menu-action-map.json")
    schemas = contract["components"]["schemas"]
    usage = collections.defaultdict(set)
    operations = []
    for path, path_item in contract["paths"].items():
        for method, operation in path_item.items():
            if method not in METHODS:
                continue
            module = module_for_path(path)
            explicit_menu = menu_map.get("route_exceptions", {}).get(f"{method.upper()} {path}", {}).get("menu")
            permission = operation.get("x-permission")
            if explicit_menu:
                module = explicit_menu
            elif isinstance(permission, str) and permission in menu_map["actions"]:
                module = menu_map["actions"][permission]
            operation_id = operation["operationId"]
            operations.append((module, path, method, operation))
            spec = {"path": path, "method": method.upper(), **operation}
            items.append(entry(f"API-{operation_id}", "api", module,
                               f"{method.upper()} {path}", "baseline/contracts/openapi-current.json", spec))
            for parameter in path_item.get("parameters", []) + operation.get("parameters", []):
                if "name" not in parameter:
                    continue
                item_id = f"PARAM-{operation_id}.{parameter['in']}.{parameter['name']}"
                items.append(entry(item_id, "wire_field", module, f"{method.upper()} {path} / {parameter['in']}.{parameter['name']}",
                                   "baseline/contracts/openapi-current.json", parameter))
            pending = list(refs_in(operation))
            seen = set()
            while pending:
                ref = pending.pop()
                if ref in seen:
                    continue
                seen.add(ref)
                prefix = "#/components/schemas/"
                if ref.startswith(prefix):
                    schema_name = ref[len(prefix):]
                    usage[schema_name].add(module)
                    pending.extend(refs_in(schemas[schema_name]))

    def schema_properties(schema_name: str, value: dict, path: str = ""):
        """登记内联对象/数组/组合的属性，并保留父级必填与条件限制。"""
        required = set(value.get("required", []))
        for name, prop in value.get("properties", {}).items():
            prop_path = f"{path}.{name}" if path else name
            owner_modules = sorted(usage[schema_name])
            module = owner_modules[0] if len(owner_modules) == 1 else "global"
            spec = {"schema": schema_name, "property": prop_path, "required": name in required,
                    "definition": prop, "used_by_modules": owner_modules,
                    "parent_constraints": {key: content for key, content in value.items() if key not in {"properties", "$defs"}}}
            items.append(entry(f"SCHEMA-{schema_name}.{prop_path}", "schema_field", module,
                               f"{schema_name}.{prop_path}", "baseline/contracts/openapi-current.json", spec))
            schema_properties(schema_name, prop, prop_path)
        if isinstance(value.get("items"), dict):
            schema_properties(schema_name, value["items"], path + "[]")
        for variant in ("allOf", "oneOf", "anyOf"):
            for index, nested in enumerate(value.get(variant, [])):
                schema_properties(schema_name, nested, f"{path}.{variant}[{index}]")

    for schema_name in sorted(usage):
        schema_properties(schema_name, schemas[schema_name])
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        duplicates = [key for key, count in collections.Counter(ids).items() if count > 1]
        raise ValueError(f"存在重复条目：{duplicates}")
    return items


def sync() -> dict:
    """按稳定ID合并，不重置已有状态；需求变更使旧勾选失效并留历史。"""
    ledger = read_json(LEDGER) if LEDGER.exists() else {
        "version": 1, "created_at": now(), "timezone": "Asia/Shanghai",
        "automation_id": "orbit-10", "history": [], "milestones": [], "items": [],
    }
    old = {item["id"]: item for item in ledger["items"]}
    merged = []
    for expected in expected_items():
        previous = old.pop(expected["id"], None)
        if previous and previous["spec_sha256"] == expected["spec_sha256"]:
            for key in ("development", "testing", "acceptance", "blocker", "notes"):
                expected[key] = copy.deepcopy(previous[key])
        elif previous:
            ledger["history"].append({"at": now(), "reason": "需求定义变化，旧结论需重验", "previous": previous})
            expected["notes"] = "需求定义已变化；旧证据保存在history，三个阶段需要重核。"
        merged.append(expected)
    for removed in old.values():
        ledger["history"].append({"at": now(), "reason": "条目不再出现在基线，需人工复核", "previous": removed})
    ledger["items"] = merged
    ledger["updated_at"] = now()
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ledger


def verify(ledger: dict) -> list[str]:
    """验证完整覆盖、状态顺序和证据，不运行或冒充产品验收。"""
    issues = []
    expected = {item["id"]: item for item in expected_items()}
    actual = {item["id"]: item for item in ledger["items"]}
    if len(actual) != len(ledger["items"]):
        issues.append("台账存在重复ID")
    for missing in sorted(expected.keys() - actual.keys()):
        issues.append(f"遗漏条目：{missing}")
    for extra in sorted(actual.keys() - expected.keys()):
        issues.append(f"基线没有此活动条目：{extra}")
    for item_id, item in actual.items():
        if item_id in expected and item["spec_sha256"] != expected[item_id]["spec_sha256"]:
            issues.append(f"{item_id} 规则发生变化，先执行sync并重新验收")
        if digest(item["spec"]) != item["spec_sha256"]:
            issues.append(f"{item_id} 台账内定义与hash不一致")
        if item["module"] not in MODULES:
            issues.append(f"{item_id} 模块不存在")
        for phase in ("development", "testing", "acceptance"):
            state = item[phase]
            allowed = {"NOT_STARTED", "IN_PROGRESS", "DONE", "BLOCKED"} if phase == "development" else {"NOT_RUN", "RUNNING", "PASS", "FAIL", "BLOCKED"}
            if state["status"] not in allowed:
                issues.append(f"{item_id}/{phase} 状态非法")
            finished = state["status"] == ("DONE" if phase == "development" else "PASS")
            if not finished:
                continue
            if not state["evidence"]:
                issues.append(f"{item_id}/{phase} 缺少完成证据")
            for filename in state["evidence"]:
                path = (ROOT / filename).resolve()
                if not path.is_relative_to(ROOT) or not path.is_file():
                    issues.append(f"{item_id}/{phase} 证据路径非法或不存在：{filename}")
                    continue
                if phase != "development":
                    try:
                        receipt = read_json(path)
                        if not (receipt["result"] == "PASS" and receipt["exit_code"] == 0
                                and receipt["phase"] == phase and item_id in receipt["item_ids"]
                                and receipt["command"] and receipt["executed_at"] and receipt["environment"]):
                            issues.append(f"{item_id}/{phase} 证据未明确证明本项通过")
                        if not receipt.get("source_sha256"):
                            issues.append(f"{item_id}/{phase} 缺少受测源码hash，不能防止旧证据误沿用")
                        for source, checksum in receipt.get("source_sha256", {}).items():
                            source_path = (ROOT / source).resolve()
                            if not source_path.is_relative_to(ROOT) or not source_path.is_file() or hashlib.sha256(source_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != checksum:
                                issues.append(f"{item_id}/{phase} 受测源码已变化或不存在，需要重新验证")
                    except (ValueError, KeyError, TypeError):
                        issues.append(f"{item_id}/{phase} 需要结构化实际执行回执")
        if item["testing"]["status"] == "PASS" and item["development"]["status"] != "DONE":
            issues.append(f"{item_id} 测试通过但开发未完成")
        if item["acceptance"]["status"] == "PASS" and item["testing"]["status"] != "PASS":
            issues.append(f"{item_id} 验收通过但测试未通过")
        if any(item[phase]["status"] == "BLOCKED" for phase in ("development", "testing", "acceptance")) and not item["blocker"]:
            issues.append(f"{item_id} 阻断没有写解除条件")
    return issues


def escape(value) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).replace("|", "&#124;").replace("\n", "<br>").replace("\r", "")


def mark(item: dict, phase: str) -> str:
    """只有本阶段完成才显示勾选；其他状态同时显示中文原因。"""
    status = item[phase]["status"]
    complete = status == ("DONE" if phase == "development" else "PASS")
    return ("[x] " if complete else "[ ] ") + LABELS[status]


def rows(items: list[dict], field_details: bool = False) -> list[str]:
    lines = ["| 编号与条目 | 开发 | 测试 | 验收 | 逻辑/证据/阻断 |", "| --- | --- | --- | --- | --- |"]
    for item in items:
        info = item["spec"] if field_details else item.get("notes", "")
        if field_details and item["kind"] == "field":
            field = item["spec"]
            info = "；".join(f"{label}：{escape(field.get(key, '按服务端合同'))}" for key, label in (
                ("required", "必填"), ("default", "默认"), ("constraints", "约束"), ("logic", "逻辑"), ("authority", "依据")))
        elif field_details and item["kind"] == "config_field":
            field = item["spec"]
            info = f"启用时必填：{'是' if field['required_when_enabled'] else '否'}；类型：{field['type']}；默认：{escape(field['default'])}；范围/长度：{field['minimum']}至{field['maximum']}；枚举：{escape(field['options'])}；逻辑：{field['logic']}"
        if not field_details and item["kind"] == "requirement":
            info = item["spec"].get("user_override", item["spec"].get("acceptance", ""))
        evidence = [filename for phase in ("development", "testing", "acceptance") for filename in item[phase]["evidence"]]
        if item["blocker"]:
            info = f"{escape(info)}<br>阻断：{escape(item['blocker'])}"
        if evidence:
            info = f"{escape(info)}<br>证据：" + ", ".join(sorted(set(evidence)))
        lines.append(f"| `{escape(item['id'])}` {escape(item['title'])} | {mark(item, 'development')} | {mark(item, 'testing')} | {mark(item, 'acceptance')} | {escape(info)} |")
    return lines


def render(ledger: dict) -> None:
    """生成面向用户的分模块表；字段/接口分册，避免总览淹没重点。"""
    checked = verify(ledger)
    if checked:
        raise ValueError("\n".join(checked))
    items = ledger["items"]
    stamp = ledger["updated_at"]
    lines = ["# ORBIT 开发、测试、验收进度", "", f"台账更新时间：{stamp}（北京时间）。", "",
             "**业务是否完成以本台账逐条证据为准。文档已整理、若依底座已下载不等于业务已开发。**", "",
             "每项分别列出开发、测试、验收。`[x]`表示该阶段真实完成；`[ ]`表示尚未完成。统计按条目数量，不按工时加权，不能作为剩余工期估算。", "",
             "入口：[全部模块逻辑](MODULE_LOGIC.md) · [逐字段逻辑与勾选](FIELD_MATRIX.md) · [接口逐项勾选](API_MATRIX.md) · [实施顺序](IMPLEMENTATION_PLAN.md)", "",
             "## 总览", "", "| 模块 | 台账条目 | 已开发 | 测试通过 | 验收通过 | 阻断条目 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for module, title in MODULES.items():
        selected = [item for item in items if item["module"] == module]
        counters = [sum(item[phase]["status"] == status for item in selected) for phase, status in (("development", "DONE"), ("testing", "PASS"), ("acceptance", "PASS"))]
        blocked = sum(any(item[phase]["status"] == "BLOCKED" for phase in ("development", "testing", "acceptance")) for item in selected)
        lines.append(f"| {title} | {len(selected)} | {counters[0]} | {counters[1]} | {counters[2]} | {blocked} |")
    counts = collections.Counter(item["kind"] for item in items)
    lines += ["", "台账分层（不同层不能当作相同工作量相加估算）：", ""]
    for kind, title in (("requirement", "原需求"), ("behavior", "业务逻辑/页面/弹窗/流程"), ("field", "基础与扩展字段"), ("config_field", "新增系统配置字段"), ("identity_field", "系统人员正文补充属性（读写分列）"), ("api", "原HTTP操作"), ("config_api", "新增系统配置接口"), ("directory_api", "新增组织目录接口"), ("wire_field", "原接口参数"), ("schema_field", "原活动Schema属性")):
        lines.append(f"- {title}：{counts[kind]}项。")
    lines += ["", "## 已完成的准备工作（不计入业务完成率）", ""]
    for milestone in ledger.get("milestones", []):
        lines.append(f"- [{'x' if milestone['done'] else ' '}] {milestone['title']}；证据：{milestone['evidence']}")
    for module, title in MODULES.items():
        lines += ["", f"## {title}", "", "逐字段、接口及Schema属性在分册中；下表列原需求与可见业务/界面条目。", ""]
        lines += rows([item for item in items if item["module"] == module and item["kind"] in {"requirement", "behavior"}])
    lines += ["", "## 外部实测准备", "", "以下依赖尚未在本任务验证，不代表已提供或已连接：OIDC、Meta应用与沙箱资产、AdsPower设备/证书、GPT/Claude API Key、对象存储、通知服务、权威余额来源、真实模型评估负责人。", "",
              "缺少依赖只阻断对应真实验收；内部业务继续开发和测试。无正在运行的开发进程时，监督必须如实报告，不以定时任务存在声称开发持续运行。", ""]
    (DOCS / "PROGRESS.md").write_text("\n".join(lines), encoding="utf-8")

    field_lines = ["# ORBIT 逐字段逻辑与开发/测试/验收", "", f"更新时间：{stamp}。原字段对象完整保留，不以生成本文件作为业务通过证据。", "",
                   "基础/扩展字段、HTTP参数与Schema属性是不同覆盖层；同一业务字段可能出现多次。正文只读信息另外登记在MODULE_LOGIC.md的对应条目中。", ""]
    for kind, title in (("field", "基础116项与扩展22项"), ("config_field", "用户新增系统配置字段（扩展合同，Python逐项核对）"), ("identity_field", "系统人员正文补充属性（读写分列）"), ("wire_field", "HTTP路径/查询/Header参数"), ("schema_field", "活动接口可达Schema属性")):
        field_lines += [f"## {title}", ""] + rows([item for item in items if item["kind"] == kind], True) + [""]
    (DOCS / "FIELD_MATRIX.md").write_text("\n".join(field_lines), encoding="utf-8")
    api_lines = ["# ORBIT 接口逐项开发/测试/验收", "", f"更新时间：{stamp}。原合同127条路径、156个HTTP操作。", "",
                 "新增系统配置接口在实现时另列版本化扩展合同；不修改原产品合同，也不因原合同没写而免除测试。", ""]
    api_lines += rows([item for item in items if item["kind"] in {"api", "config_api", "directory_api"}])
    (DOCS / "API_MATRIX.md").write_text("\n".join(api_lines) + "\n", encoding="utf-8")
    mirror_reports()


def mirror_reports() -> None:
    """仅在本任务工作区镜像用户入口；Git仓库内文件才是状态源。"""
    workspace = ROOT.parent
    if ROOT.name != "orbit-server" or not (workspace / "data" / "ORBIT_Codex开发PRD").is_dir():
        return
    mirror = workspace / "docs"
    mirror.mkdir(exist_ok=True)
    for filename in ("README.md", "PROGRESS.md", "MODULE_LOGIC.md", "IMPLEMENTATION_PLAN.md", "SYSTEM_CONFIGURATION.md", "MYSQL_INTEGRATION.md", "HTTP_SECURITY_TESTS.md", "NETWORK_INTEGRATION.md", "BROWSER_INTEGRATION.md", "ANALYSIS_INPUT.md", "ANALYSIS_JOBS.md", "RULE_SCHEDULE.md", "RULE_CONDITIONS.md", "RULE_DRAFTS.md", "RULE_OWNERSHIP.md", "METRIC_PROFILES.md", "ACCOUNT_SCOPES.md", "SCOPE_HTTP.md", "AUDIT_QUERY.md", "PYTHON_BACKEND_MIGRATION.md", "DATABASE_DESIGN.md", "PYTHON_CONFIGURATION.md", "PYTHON_IDENTITY.md", "PYTHON_AUTHENTICATION.md", "NATIVE_DIRECTORY_BOUNDARIES.md", "FIELD_MATRIX.md", "API_MATRIX.md", "progress.json", "DELIVERY_BOARD.md"):
        (mirror / filename).write_bytes((DOCS / filename).read_bytes())
    readme = mirror / "README.md"
    # 新业务交付说明同步到用户入口；仅镜像受控文档，不复制基线、运行产物或私有配置。
    for pattern in ("ACCOUNT_*.md", "MATERIAL_*.md", "CHANNEL_*.md", "LAUNCH_*.md", "TASK_*.md", "PYTHON_LAUNCH_DELIVERY.md"):
        for document in DOCS.glob(pattern):
            (mirror / document.name).write_bytes(document.read_bytes())
    readme.write_text(readme.read_text(encoding="utf-8").replace("(baseline/README.md)", "(../orbit-server/docs/orbit/baseline/README.md)"), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("sync", "render", "check"))
    args = parser.parse_args()
    ledger = sync() if args.command == "sync" else read_json(LEDGER)
    issues = verify(ledger)
    if issues:
        for issue in issues:
            print(issue)
        return 1
    if args.command in {"sync", "render"}:
        render(ledger)
    print(json.dumps({"status": "PASS", "scope": "仅台账完整性与证据规则，不是产品功能验收", "items": len(ledger["items"]),
                      "counts": dict(collections.Counter(item["kind"] for item in ledger["items"]))}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
