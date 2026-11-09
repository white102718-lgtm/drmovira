"""登记本次真实准备工作和首批配置源码；不批量勾选业务完成。"""

import json
import subprocess
from pathlib import Path

import orbit_progress as progress


def main():
    ledger = progress.read_json(progress.LEDGER)
    if ledger.get("initial_checkpoint_recorded_at"):
        raise RuntimeError("初始检查点已登记；后续应更新现有条目与证据，禁止重置里程碑")
    receipt = progress.read_json(progress.DOCS / "evidence/java-tests-and-compile.json")
    if receipt["result"] != "PASS" or receipt["summary"]["failures"] or receipt["summary"]["errors"] or receipt["summary"]["skipped"]:
        raise RuntimeError("本阶段Java校验尚未全部通过，不能登记加密测试完成")

    working = {"CFG-01", "CFG-02", "CFG-04", "CFG-05", "CFG-06", "CFG-08", "CFG-09", "CFG-10", "CFG-11", "CFG-12", "CFG-13", "CFG-14", "CFG-15", "CFG-16"}
    for item in ledger["items"]:
        if (item["id"] in working or item["kind"] in {"config_field", "config_api"}) and item["development"]["status"] == "NOT_STARTED":
            item["development"]["status"] = "IN_PROGRESS"
            item["notes"] = "已加入配置表单、字段白名单、服务及SQL首批源码；完整数据库/E2E、配置消费者和剩余工作未验收。"
        if item["id"] == "CFG-07" and item["acceptance"]["status"] != "PASS":
            item["development"] = {"status": "DONE", "evidence": ["ruoyi-system/src/main/java/com/ruoyi/system/orbit/config/SecretCipher.java"]}
            item["testing"] = {"status": "PASS", "evidence": ["docs/orbit/evidence/java-tests-and-compile.json"]}
            item["notes"] = "加密库随机nonce、认证绑定、篡改拒绝、跨租户/配置/slot拒绝和密钥轮换单测已通过；数据库及整体配置验收仍未通过。"

    snapshot = {"captured_at": progress.now(), "scope": "准备工作与本阶段证据，不代表全产品完成", "automation_id": "orbit-10", "repositories": []}
    for folder, repository in ((progress.ROOT, "orbit-server"), (progress.ROOT.parent / "orbit-web", "orbit-web")):
        metadata = json.loads(subprocess.check_output(["gh", "repo", "view", "hesong0105-bit/" + repository, "--json", "nameWithOwner,isPrivate,url"], cwd=folder))
        if not metadata["isPrivate"]:
            raise RuntimeError("仓库可见性不是已确认的私有，拒绝登记")
        metadata["local_branch"] = subprocess.check_output(["git", "branch", "--show-current"], cwd=folder, text=True).strip()
        metadata["upstream_sha"] = subprocess.check_output(["git", "rev-parse", "upstream/" + metadata["local_branch"]], cwd=folder, text=True).strip()
        snapshot["repositories"].append(metadata)
    original = progress.ROOT.parent / "data/ORBIT_Codex开发PRD"
    differences = [str(path.relative_to(original)) for path in original.rglob("*") if path.is_file()
                   and path.read_bytes() != (progress.BASELINE / path.relative_to(original)).read_bytes()]
    if differences:
        raise RuntimeError("产品基线副本与原文件不一致，拒绝登记")
    snapshot["baseline_files_byte_equal"] = sum(path.is_file() for path in original.rglob("*"))
    (progress.DOCS / "evidence/preparation.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    ledger["milestones"] = [
        {"done": True, "title": "已记录官方若依Vue3/Element Plus/Java技术覆盖与完整实施顺序", "evidence": "IMPLEMENTATION_PLAN.md"},
        {"done": True, "title": "已保留产品原始需求，副本逐文件字节相等；18组静态需求校验通过", "evidence": "evidence/preparation.json、evidence/prd-baseline.json"},
        {"done": True, "title": "已登记需求正文的模块逻辑、页面/弹窗、字段、参数、Schema及接口操作，并分开开发/测试/验收", "evidence": "MODULE_LOGIC.md、progress.json、evidence/tracker-tests.json"},
        {"done": True, "title": "已下载官方前后端底座并创建两个GitHub私有仓库", "evidence": "evidence/preparation.json"},
        {"done": True, "title": "当前聊天已创建每10分钟进度监督", "evidence": "automation:orbit-10"},
        {"done": True, "title": "已完成本阶段Java单测/编译、前端格式/类型/组件测试/构建；不是全业务验收", "evidence": "evidence/initial-checks.json"},
        {"done": False, "title": "逐个打开参考原型全部交互并与覆盖台账复核，补登记额外交互", "evidence": "原型交互核对仍待执行，不以文档覆盖替代"},
        {"done": False, "title": "八模块全部开发、测试、验收和最终推送", "evidence": "仍按下方逐项台账执行，不能提前勾选"},
    ]
    ledger["updated_at"] = progress.now()
    ledger["initial_checkpoint_recorded_at"] = ledger["updated_at"]
    progress.LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    progress.render(ledger)
    print(json.dumps({"checkpoint": "initial", "business_developed": sum(item["development"]["status"] == "DONE" for item in ledger["items"]),
                      "testing_passed": sum(item["testing"]["status"] == "PASS" for item in ledger["items"]),
                      "acceptance_passed": sum(item["acceptance"]["status"] == "PASS" for item in ledger["items"])}))


if __name__ == "__main__":
    main()
