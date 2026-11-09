"""验证进度台账不会漏项、丢历史或无证据勾选；不是产品功能测试。"""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "orbit_progress.py"
SPEC = importlib.util.spec_from_file_location("orbit_progress", MODULE_PATH)
progress = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(progress)


class ProgressIntegrityTest(unittest.TestCase):
    """用实际合同验证覆盖；用隔离fixture验证证据和状态约束。"""

    def fixture(self):
        return progress.entry("CASE-1", "behavior", "system", "测试条目", "fixture", {"logic": "不可伪造通过"})

    def verify_one(self, item):
        with patch.object(progress, "expected_items", return_value=[self.fixture()]):
            return progress.verify({"items": [item]})

    def test_contract_coverage(self):
        items = progress.expected_items()
        counts = {}
        for item in items:
            counts[item["kind"]] = counts.get(item["kind"], 0) + 1
        self.assertEqual(counts["requirement"], 36)
        self.assertEqual(counts["field"], 138)
        self.assertEqual(counts["api"], 156)
        self.assertEqual(counts["config_field"], 62)
        self.assertEqual(counts["config_api"], 7)
        self.assertEqual(counts["directory_api"], 4)
        self.assertEqual(counts["identity_field"], 21)
        self.assertTrue({"FIELD-IDENTITY-UserWrite.phone", "FIELD-IDENTITY-User.phone", "FIELD-IDENTITY-User.identity_status"}.issubset({item["id"] for item in items}))
        self.assertIn("CFG-16", {item["id"] for item in items})
        self.assertTrue(all(item["module"] in progress.MODULES for item in items))
        self.assertEqual(len(items), len({item["id"] for item in items}))

    def test_unstarted_is_not_a_business_pass(self):
        item = self.fixture()
        self.assertEqual(self.verify_one(item), [])
        self.assertIn("[ ]", progress.mark(item, "acceptance"))

    def test_interface_ownership_follows_menu_contract_not_only_path_names(self):
        operations = [item for item in progress.expected_items() if item["kind"] == "api"]
        launch_stats = [item for item in operations if item["spec"]["path"].startswith("/api/v1/launch-stats")]
        self.assertTrue(launch_stats)
        self.assertTrue(all(item["module"] == "launch" for item in launch_stats))
        agents = [item for item in operations if item["spec"]["path"].startswith("/api/v1/execution-agents")]
        self.assertTrue(agents)
        self.assertTrue(all(item["module"] == "environments" for item in agents))

    def test_complete_without_evidence_is_rejected(self):
        item = self.fixture()
        item["development"]["status"] = "DONE"
        self.assertTrue(any("缺少完成证据" in issue for issue in self.verify_one(item)))

    def test_acceptance_cannot_skip_testing(self):
        item = self.fixture()
        item["acceptance"]["status"] = "PASS"
        self.assertTrue(any("测试未通过" in issue for issue in self.verify_one(item)))

    def test_blocker_requires_reason(self):
        item = self.fixture()
        item["testing"]["status"] = "BLOCKED"
        self.assertTrue(any("解除条件" in issue for issue in self.verify_one(item)))

    def test_tampered_definition_is_rejected(self):
        item = self.fixture()
        item["spec"]["logic"] = "改成任意通过"
        self.assertTrue(any("hash不一致" in issue for issue in self.verify_one(item)))

    def test_evidence_must_match_item_phase_and_real_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.java").write_text("// fixture", encoding="utf-8")
            receipt = {"item_ids": ["OTHER"], "phase": "testing", "result": "PASS", "exit_code": 0,
                       "command": "fixture", "executed_at": progress.now(), "environment": "isolated fixture",
                       "source_sha256": {"source.java": progress.hashlib.sha256((root / "source.java").read_bytes()).hexdigest()}}
            (root / "run.json").write_text(json.dumps(receipt), encoding="utf-8")
            item = self.fixture()
            item["development"] = {"status": "DONE", "evidence": ["source.java"]}
            item["testing"] = {"status": "PASS", "evidence": ["run.json"]}
            with patch.object(progress, "ROOT", root):
                self.assertTrue(any("未明确证明本项" in issue for issue in self.verify_one(item)))
                receipt["item_ids"] = ["CASE-1"]
                (root / "run.json").write_text(json.dumps(receipt), encoding="utf-8")
                self.assertEqual(self.verify_one(item), [])

    def test_sync_preserves_state_and_invalidates_changed_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            original = self.fixture()
            original["development"]["status"] = "IN_PROGRESS"
            original["notes"] = "保留本条当前进度"
            ledger = {"items": [original], "history": [], "milestones": []}
            path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
            with patch.object(progress, "LEDGER", path), patch.object(progress, "expected_items", return_value=[self.fixture()]):
                merged = progress.sync()
                self.assertEqual(merged["items"][0]["development"]["status"], "IN_PROGRESS")
                self.assertEqual(merged["items"][0]["notes"], "保留本条当前进度")
            changed = copy.deepcopy(self.fixture())
            changed["spec"]["logic"] = "规则发生真实变更"
            changed["spec_sha256"] = progress.digest(changed["spec"])
            with patch.object(progress, "LEDGER", path), patch.object(progress, "expected_items", return_value=[changed]):
                merged = progress.sync()
                self.assertEqual(merged["items"][0]["development"]["status"], "NOT_STARTED")
                self.assertEqual(len(merged["history"]), 1)


if __name__ == "__main__":
    unittest.main()
