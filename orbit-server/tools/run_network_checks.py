"""执行真实网络HTTP/JWT/Redis/MySQL联合测试，生成脱敏回执。"""
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
    command = [args.maven, "-B", "-ntp", "-pl", "ruoyi-admin", "-am", "-Porbit-network-it", "verify"]
    import time
    started = time.time()
    receipt, _ = execute("network-configuration-integration", command, ROOT, environment)
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
    receipt["scope"] = "真实回环TCP HTTP、Tomcat、若依JWT签名/Redis会话、MySQL/Mapper/事务/安全链；仅平台传输fixture；未含浏览器、用户名密码登录流程、完整应用或真实平台验收"
    receipt["environment"] = '本机Windows真实回环HTTP/Tomcat、JWT签名、Redis社区构建8.10.3及MySQL8.4.13；仅外部平台传输fixture，未验证浏览器或完整应用'
    receipt["phase"] = "testing"
    receipt["item_ids"] = ["API-CFG-getSystemConfigurationMetadata"] if receipt["result"] == "PASS" else []
    files = list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/config").glob("*.java"))
    files += list((ROOT / "sql/orbit").glob("*.sql"))
    files += list((ROOT / "ruoyi-admin/src/main/java/com/ruoyi/web/controller/orbit").glob("*.java"))
    files += list((ROOT / "ruoyi-admin/src/main/java/com/ruoyi/web/config/orbit").glob("*.java"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/ConfigurationMapper.xml", ROOT / "ruoyi-admin/src/test/java/com/ruoyi/web/controller/orbit/OrbitConfigurationNetworkIT.java", ROOT / "ruoyi-admin/src/main/resources/mybatis/mybatis-config.xml", ROOT / "ruoyi-admin/pom.xml", ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/TokenService.java", ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/config/RedisConfig.java", ROOT / "ruoyi-admin/src/test/resources/logback-orbit-test.xml"]
    files += [ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java", ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/security/filter/JwtAuthenticationTokenFilter.java", ROOT / "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/PermissionService.java", ROOT / "ruoyi-common/src/main/java/com/ruoyi/common/core/redis/RedisCache.java", ROOT / "sql/ry_20260417.sql"]
    receipt["source_sha256"] = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for path in files}
    destination = EVIDENCE / "network-configuration-integration.json"
    if destination.exists():
        previous = json.loads(destination.read_text(encoding="utf-8"))
        archive = EVIDENCE / ("network-configuration-integration-" + previous["executed_at"].replace(":", "").replace("+", "_") + ".json")
        if not archive.exists():
            archive.write_bytes(destination.read_bytes())
    destination.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": receipt["result"], "summary": counts}))
    return 0 if receipt["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
