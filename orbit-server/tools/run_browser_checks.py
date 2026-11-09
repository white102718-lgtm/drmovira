"""执行完整若依应用与Chromium浏览器集成测试，生成脱敏回执。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from run_orbit_checks import execute, ROOT, EVIDENCE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", required=True)
    parser.add_argument("--maven", required=True)
    args = parser.parse_args()
    environment = os.environ.copy()
    environment["JAVA_HOME"] = args.java_home
    environment["PATH"] = str(Path(args.java_home) / "bin") + os.pathsep + environment["PATH"]
    command = [args.maven, "-B", "-ntp", "-pl", "ruoyi-admin", "-am", "-Porbit-browser-it", "verify"]
    import time
    started = time.time()
    receipt, _ = execute("application-browser-integration", command, ROOT, environment)
    reports = list((ROOT / "ruoyi-admin/target/failsafe-reports").glob("TEST-*.xml"))
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    cases = []
    for path in reports:
        if path.stat().st_mtime < started:
            continue
        suite = ET.parse(path).getroot()
        for key in counts:
            counts[key] += int(suite.get(key, "0"))
        cases.extend(case.get("name") for case in suite.findall("testcase"))
    if not counts["tests"] or counts["failures"] or counts["errors"] or counts["skipped"]:
        receipt["result"] = "FAIL"
    receipt["summary"] = {**counts, "cases": cases}
    unit_counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for path in ROOT.glob("ruoyi-*/target/surefire-reports/TEST-*.xml"):
        if path.stat().st_mtime < started:
            continue
        suite = ET.parse(path).getroot()
        for key in unit_counts:
            unit_counts[key] += int(suite.get(key, "0"))
    receipt["unit_summary"] = unit_counts
    report = ROOT.parent / ".runtime/browser-it/playwright-result.json"
    if report.is_file() and report.stat().st_mtime >= started:
        browser = json.loads(report.read_text(encoding="utf-8"))
        receipt["browser_summary"] = browser.get("stats", {})
    else:
        receipt["browser_summary"] = {"not_run": True}
    stats = receipt["browser_summary"]
    if stats.get("expected") != 9 or stats.get("unexpected", 0) or stats.get("skipped", 0) or stats.get("flaky", 0):
        receipt["result"] = "FAIL"
    receipt["scope"] = "完整RuoYiApplication、真实账号密码登录/动态菜单/Chromium配置、账户范围与审计页面、MySQL/Redis；验证码在独立fixture关闭，仅平台探测fixture；不代表全部模块或真实平台验收"
    receipt["environment"] = '本机Windows完整若依应用、Chromium、MySQL8.4.13及Redis社区构建8.10.3；原登录无验证码fixture，平台传输fixture'
    receipt["phase"] = "testing"
    receipt["item_ids"] = []
    files = list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/config").glob("*.java"))
    files += list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/rules").glob("*.java"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/RuleDraftMapper.xml"]
    files += list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/metrics").glob("*.java"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/MetricProfileMapper.xml"]
    files += list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/scope").glob("*.java"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/AccountScopeMapper.xml"]
    files += list((ROOT / "sql/orbit").glob("*.sql"))
    files += list((ROOT / "ruoyi-admin/src/main/java/com/ruoyi/web/controller/orbit").glob("*.java"))
    files += list((ROOT / "ruoyi-admin/src/main/java/com/ruoyi/web/config/orbit").glob("*.java"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/ConfigurationMapper.xml", ROOT / "ruoyi-admin/src/test/java/com/ruoyi/web/controller/orbit/OrbitApplicationBrowserIT.java", ROOT / "ruoyi-admin/src/test/java/com/ruoyi/web/controller/orbit/OrbitConfigurationNetworkIT.java", ROOT / "ruoyi-admin/src/main/resources/mybatis/mybatis-config.xml", ROOT / "ruoyi-admin/pom.xml", ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/TokenService.java", ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/config/RedisConfig.java", ROOT / "ruoyi-admin/src/test/resources/logback-orbit-test.xml"]
    files += [ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java", ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/security/filter/JwtAuthenticationTokenFilter.java", ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/PermissionService.java", ROOT / "ruoyi-common/src/main/java/com/ruoyi/common/core/redis/RedisCache.java", ROOT / "sql/ry_20260417.sql"]
    files += [ROOT / "ruoyi-admin/src/main/java/com/ruoyi/RuoYiApplication.java", ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/config/DruidConfig.java", ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/config/MyBatisConfig.java", ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysMenuServiceImpl.java"]
    files += list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/analysis").glob("*.java"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/AnalysisJobMapper.xml", ROOT / "ruoyi-system/src/main/resources/orbit/analysis-input.schema.json", ROOT / "ruoyi-system/pom.xml"]
    frontend = ROOT.parent / "orbit-web"
    frontend_files = [frontend / "playwright.orbit.config.ts", frontend / "tests/e2e/orbit-configuration.spec.ts", frontend / "vite.config.js", frontend / "package.json", frontend / "pnpm-lock.yaml"]
    frontend_files += list((frontend / "src/views/orbit/system/configuration").glob("*.vue"))
    frontend_files += list((frontend / "src/views/orbit/accounts/scopes").glob("*.vue"))
    frontend_files += [frontend / "src/api/orbit/scopes.ts", frontend / "tests/e2e/orbit-scopes.spec.ts"]
    frontend_files += [frontend / "src/api/orbit/configuration.ts", frontend / "src/api/orbit/audit.ts", frontend / "tests/e2e/orbit-audit.spec.ts"]
    frontend_files += list((frontend / "src/views/orbit/system/audit").glob("*.vue"))
    receipt["frontend_source_sha256"] = {str(path.relative_to(frontend)).replace("\\", "/"): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for path in frontend_files}
    receipt["source_sha256"] = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for path in files}
    destination = EVIDENCE / "application-browser-integration.json"
    if destination.exists():
        previous = json.loads(destination.read_text(encoding="utf-8"))
        archive = EVIDENCE / ("application-browser-integration-" + previous["executed_at"].replace(":", "").replace("+", "_") + ".json")
        if not archive.exists():
            archive.write_bytes(destination.read_bytes())
    destination.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": receipt["result"], "summary": counts}))
    return 0 if receipt["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
