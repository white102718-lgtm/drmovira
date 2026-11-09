"""旧测试报告不能让当前未执行的测试产生通过证据。"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "run_orbit_checks.py"
SPEC = importlib.util.spec_from_file_location("orbit_checks", SOURCE)
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)


class FreshJavaReportTest(unittest.TestCase):
    def report(self, directory, name, modified, tests, failures=0):
        report = Path(directory) / "ruoyi-system/target/surefire-reports" / name
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(f'<testsuite tests="{tests}" failures="{failures}" errors="0" skipped="0"><testcase name="{name}"/></testsuite>', encoding="utf-8")
        os.utime(report, (modified, modified))

    def test_old_success_cannot_count_as_current_execution(self):
        with tempfile.TemporaryDirectory(prefix="orbit-report-fixture-") as directory:
            self.report(directory, "TEST-old.xml", 1000, 999)
            counts, cases = checks.java_report_summary(Path(directory), 1001)
            self.assertEqual(0, counts["tests"])
            self.assertEqual([], cases)

    def test_only_fresh_reports_contribute_success_and_failure_counts(self):
        with tempfile.TemporaryDirectory(prefix="orbit-report-fixture-") as directory:
            self.report(directory, "TEST-old.xml", 1000, 999, 999)
            self.report(directory, "TEST-new.xml", 1002, 2, 1)
            counts, cases = checks.java_report_summary(Path(directory), 1001)
            self.assertEqual({"tests": 2, "failures": 1, "errors": 0, "skipped": 0}, counts)
            self.assertEqual(["TEST-new.xml"], cases)
