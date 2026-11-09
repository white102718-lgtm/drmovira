"""执行独立MySQL8配置集成测试，生成脱敏回执；不会连接可配置外部数据库。"""
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
    command = [args.maven, "-B", "-ntp", "-pl", "ruoyi-system", "-am", "-Porbit-mysql-it", "verify"]
    import time
    started = time.time()
    receipt, _ = execute("mysql-configuration-integration", command, ROOT, environment)
    reports = list((ROOT / "ruoyi-system/target/failsafe-reports").glob("TEST-*.xml"))
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
    receipt["scope"] = "真实MySQL8、本工作区13306独立实例；原若依SQL与V001-019、MyBatis映射、Spring事务回滚、幂等并发、版本CAS、租户与历史、分析入队冻结/并发/冷却/当地日额度/回滚、规则草稿版本/幂等/状态/租户/回滚/实时所有权授权、指标口径冻结/版本/回滚/未验证阻断、账户目录CAS/范围冻结/当前授权版本触发器/迁移重放/溢出/回滚、冻结成员分页/AEAD游标/5万成员250页、内部会话目标冻结/双版本绑定/旧快照失效/目录门闩锁序并发、冻结成功审计/幂等并发/失败回滚、公开跨租户目标/成员定位/歧义拒绝、冻结审计历史身份/当前菜单及数据读取门禁/首个HTTP请求UUID与重放不覆盖/内部审计有界扫描与游标/公开审计全租户归并与合同投影；不包含HTTP/Redis/浏览器/真实平台验收"
    receipt["environment"] = "本机Windows、Java21、真实独立MySQL8.4.13、MyBatis与Spring事务；仅平台传输为fixture"
    receipt["phase"] = "testing"
    receipt["item_ids"] = []
    files = list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/config").glob("*.java"))
    files += list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/analysis").glob("*.java"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/AnalysisJobMapper.xml", ROOT / "ruoyi-system/src/main/resources/orbit/analysis-input.schema.json"]
    files += list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/rules").glob("*.java"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/RuleDraftMapper.xml", ROOT / "ruoyi-system/src/test/java/com/ruoyi/system/orbit/rules/RuleWriteGuardTest.java"]
    files += list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/metrics").glob("*.java"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/MetricProfileMapper.xml", ROOT / "ruoyi-system/src/test/java/com/ruoyi/system/orbit/metrics/MetricProfileGuardTest.java"]
    files += list((ROOT / "ruoyi-system/src/main/java/com/ruoyi/system/orbit/scope").glob("*.java"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/AccountScopeMapper.xml", ROOT / "ruoyi-system/src/test/java/com/ruoyi/system/orbit/scope/ScopeRequestGuardTest.java"]
    files += list((ROOT / "sql/orbit").glob("*.sql"))
    files += [ROOT / "ruoyi-system/src/main/resources/mapper/orbit/ConfigurationMapper.xml", ROOT / "ruoyi-system/src/test/java/com/ruoyi/system/orbit/config/ConfigurationMySqlIT.java", ROOT / "ruoyi-admin/src/main/resources/mybatis/mybatis-config.xml", ROOT / "ruoyi-system/pom.xml"]
    receipt["source_sha256"] = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for path in files}
    destination = EVIDENCE / "mysql-configuration-integration.json"
    if destination.exists():
        previous = json.loads(destination.read_text(encoding="utf-8"))
        archive = EVIDENCE / ("mysql-configuration-integration-" + previous["executed_at"].replace(":", "").replace("+", "_") + ".json")
        if not archive.exists():
            archive.write_bytes(destination.read_bytes())
    destination.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": receipt["result"], "summary": counts}))
    return 0 if receipt["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
