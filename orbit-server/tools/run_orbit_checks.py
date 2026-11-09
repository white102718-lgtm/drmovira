"""运行本阶段实际校验并保存脱敏回执；不把单测/构建标记为全业务验收。"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/orbit/evidence"


def execute(name, command, cwd, env=None):
    """只输出名称与退出码；第三方诊断不直接传播到用户日志。"""
    started = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True)
    text = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
    receipt = {"name": name, "result": "PASS" if result.returncode == 0 else "FAIL", "exit_code": result.returncode,
               "command": subprocess.list2cmdline([str(value) for value in command]), "executed_at": started,
               "environment": "本地开发验证；模拟传输/Mapper的测试不代表真实平台或MySQL集成", "summary": {}}
    print(json.dumps({"check": name, "result": receipt["result"], "exit_code": result.returncode}))
    if result.returncode:
        # 当前校验只使用fixture；失败日志留在系统临时目录，不入仓库和业务审计。
        descriptor, path = tempfile.mkstemp(prefix="orbit-check-failure-", suffix=".log")
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(result.stdout + result.stderr)
        print(json.dumps({"diagnostic_file": path}))
    return receipt, text


def java_report_summary(root, started):
    """只采集本轮生成的Surefire报告，旧成功/失败均不混入当前测试证据。"""
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    cases = []
    for path in root.glob("ruoyi-*/target/surefire-reports/TEST-*.xml"):
        if path.stat().st_mtime < started:
            continue
        suite = ET.parse(path).getroot()
        for key in counts:
            counts[key] += int(suite.get(key, "0"))
        cases.extend(case.get("name") for case in suite.findall("testcase"))
    return counts, cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", required=True)
    parser.add_argument("--maven", required=True)
    parser.add_argument("--frontend", required=True)
    parser.add_argument("--skip-frontend", action="store_true", help="前端未变化时复用已有回执，保持原执行时间")
    parser.add_argument("--frontend-only", action="store_true", help="只重跑发生变化的前端，复用既有后端回执")
    args = parser.parse_args()
    frontend = Path(args.frontend).resolve()
    environment = os.environ.copy()
    environment["JAVA_HOME"] = args.java_home
    environment["PATH"] = str(Path(args.java_home) / "bin") + os.pathsep + environment["PATH"]
    results = []

    if args.frontend_only:
        for name in ("tracker-tests", "prd-baseline", "java-tests-and-compile"):
            previous = json.loads((EVIDENCE / (name + ".json")).read_text(encoding="utf-8"))
            if previous["result"] != "PASS":
                raise RuntimeError("后端旧回执未通过，不能复用")
            results.append(previous)
        results.extend(frontend_checks(frontend))
        save_results(results)
        return 1 if any(result["result"] != "PASS" for result in results) else 0

    receipt, output = execute("tracker-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tools/tests", "-v"], ROOT)
    receipt["scope"] = "台账覆盖和防止无证据勾选，不是产品功能验收"
    receipt["summary"]["tests"] = int(re.search(r"Ran (\d+) tests", output).group(1)) if re.search(r"Ran (\d+) tests", output) else 0
    results.append(receipt)

    with tempfile.TemporaryDirectory(prefix="orbit-prd-check-") as directory:
        target = Path(directory).resolve()
        if not target.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise RuntimeError("需求校验临时目录不在已核实的系统临时路径内")
        shutil.copytree(ROOT / "docs/orbit/baseline", target / "baseline")
        receipt, _ = execute("prd-baseline", [sys.executable, "-X", "utf8", "validation/validate_prd.py"], target / "baseline")
        receipt["scope"] = "原产品包静态一致性；未修改原需求，不代表业务验收"
        produced = json.loads((target / "baseline/validation/result.json").read_text(encoding="utf-8"))
        receipt["summary"] = {"checks": len(produced["checks"]), "failed": produced["failed"]}
        results.append(receipt)

    java_started = dt.datetime.now(dt.timezone.utc).timestamp()
    receipt, _ = execute("java-tests-and-compile", [args.maven, "-B", "-ntp", "-pl", "ruoyi-admin", "-am", "test"], ROOT, environment)
    counts, cases = java_report_summary(ROOT, java_started)
    if not counts["tests"] or any(counts[key] for key in ("failures", "errors", "skipped")):
        receipt["result"] = "FAIL"
    receipt["summary"] = {**counts, "cases": cases}
    receipt["scope"] = "Java全模块编译、配置/加密/服务/只读探测/规则调度/三值条件核心及MockMvc Servlet安全链测试（只统计本次新报告）；Token会话存储/Mapper/平台传输为替身；真实MySQL另有专项回执，不含真实Redis/网络HTTP/浏览器/平台验收"
    receipt["phase"] = "testing"
    receipt["item_ids"] = ["CFG-07"] if receipt["result"] == "PASS" else []
    receipt["source_sha256"] = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in [ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/config/SecretCipher.java", ROOT / "ruoyi-system/src/test/java/com/ruoyi/system/orbit/config/SecretCipherTest.java"]}
    results.append(receipt)

    if args.skip_frontend:
        for name in ("frontend-format", "frontend-types", "frontend-tests", "frontend-build"):
            previous = json.loads((EVIDENCE / (name + ".json")).read_text(encoding="utf-8"))
            if previous["result"] != "PASS":
                raise RuntimeError("前端旧回执未通过，不能复用")
            results.append(previous)
    else:
        results.extend(frontend_checks(frontend))
    save_results(results)
    return 1 if any(result["result"] != "PASS" for result in results) else 0


def frontend_checks(frontend):
    results = []
    pnpm = shutil.which("pnpm.cmd") or shutil.which("pnpm")
    for name, script in (("frontend-format", "format:check:orbit"), ("frontend-types", "check:orbit"), ("frontend-tests", "test:orbit"), ("frontend-build", "build:prod")):
        receipt, output = execute(name, [pnpm, script], frontend)
        receipt["scope"] = "前端本地格式/类型/组件与请求测试/生产构建；不含真实浏览器前后端验收"
        if name == "frontend-tests":
            normalized = re.sub(r"\x1b\[[0-9;]*m", "", output)
            match = re.search(r"Tests\s+(\d+) passed", normalized)
            receipt["summary"]["passed"] = int(match.group(1)) if match else 0
        results.append(receipt)
    return results


def save_results(results):
    for receipt in results:
        (EVIDENCE / (receipt["name"] + ".json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"executed_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),
               "scope": "本阶段实际执行校验，不是全产品完成声明", "checks": [{key: value for key, value in receipt.items() if key in {"name", "result", "exit_code", "summary", "scope"}} for receipt in results]}
    (EVIDENCE / "initial-checks.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
