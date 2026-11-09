"""防止重新导出字段时丢失已实现的只读测试人工原因契约。"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "export_configuration_fields.py"
SPEC = importlib.util.spec_from_file_location("configuration_export", SOURCE)
export = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export)


class ExportRegressionTest(unittest.TestCase):
    def test_regeneration_preserves_read_test_reason_contract(self):
        fields = json.loads((export.ROOT / "docs/orbit/extensions/configuration-fields.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="orbit-contract-export-") as directory:
            export.write_openapi(fields, Path(directory))
            contract = json.loads((Path(directory) / "system-configurations.openapi.json").read_text(encoding="utf-8"))
        operation = contract["paths"]["/api/v1/system-configurations/{id}/test"]["post"]
        self.assertTrue(operation["requestBody"]["required"])
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(["reason"], schema["required"])
        self.assertEqual("string", schema["properties"]["reason"]["type"])
        self.assertEqual(500, schema["properties"]["reason"]["maxLength"])
        self.assertEqual("If-Match", operation["parameters"][1]["name"])
