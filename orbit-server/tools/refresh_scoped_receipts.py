"""从实际父回执更新限定字段证据；只接受确实执行过的具名用例和当前源码。"""

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/orbit/evidence"
TARGETS = {
    "metadata": "python-configuration-metadata.json",
    "reference-channel": "python-reference-channel-http.json",
    "account-scope": "python-account-scope-original-fields.json",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=TARGETS, required=True)
    parser.add_argument("--parent", required=True, help="证据目录内已保存的真实父回执文件名")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]+\.json", args.parent):
        parser.error("父回执必须是证据目录内的明确文件名")
    target = EVIDENCE / TARGETS[args.kind]
    parent = json.loads((EVIDENCE / args.parent).read_text(encoding="utf-8"))
    receipt = json.loads(target.read_text(encoding="utf-8"))
    selected = receipt["summary"]["cases"]
    executed = parent["summary"]["cases"]
    if not selected or len(selected) != len(set(selected)) or not set(selected) <= set(executed):
        raise ValueError("父回执未真实通过全部限定具名检查，不可刷新")
    # 只沿用先前明确的字段依赖；不把并行模块半成品扩大为已验证业务。
    source_keys = set(receipt["source_sha256"])
    if args.kind == "metadata":
        source_keys.add("tools/configuration_metadata_checks.py")
    current_sources = {}
    for name in sorted(source_keys):
        recorded = parent["source_sha256"][name]
        actual = hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if recorded != actual:
            raise ValueError(f"父回执源码已变化，必须复验：{name}")
        current_sources[name] = recorded
    for name in ("executed_at", "command", "environment", "fixture_migrations"):
        if name in parent:
            receipt[name] = parent[name]
    receipt["source_sha256"] = current_sources
    receipt["test_harness_sha256_at_execution"] = parent["source_sha256"][
        "tools/run_python_framework_checks.py"
    ]
    receipt["parent_run"] = {
        "receipt": "docs/orbit/evidence/" + args.parent,
        "result": parent["result"],
        **{key: parent["summary"][key] for key in ("passed", "failures", "not_run")},
    }
    receipt["source_scope_note"] = (
        "限定具名用例均在父回执真实执行成功，字段依赖源码与父回执一致；"
        "父回执的整体结果原样保留。无关并行模块、完整页面、容量和外部环境未因此验收。"
    )
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": target.name, "selected_passed": len(selected)}))


if __name__ == "__main__":
    main()
