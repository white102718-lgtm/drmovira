"""原始schema校验器拒绝错误类型；响应实测另由主线工具运行。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from tools.material_schema_checks import validate_original_schema


@pytest.fixture
def specification():
    return json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "data/ORBIT_Codex开发PRD/contracts/openapi-current.json"
        ).read_text(encoding="utf-8")
    )


def test_original_asset_duration_accepts_exact_decimal_string_and_null(specification):
    schema = specification["components"]["schemas"]["Asset"]["properties"]["duration_seconds"]
    for value in (None, "2.000000", "0.5"):
        validate_original_schema(value, schema, specification)
    for value in (2, 2.0, "2.0000001", "-1", "NaN"):
        with pytest.raises(AssertionError):
            validate_original_schema(value, schema, specification)


def test_original_metric_verified_requires_json_boolean(specification):
    schema = specification["components"]["schemas"]["MetricProfile"]["properties"]["verified"]
    for value in (True, False):
        validate_original_schema(value, schema, specification)
    for value in (0, 1, "true", None, []):
        with pytest.raises(AssertionError):
            validate_original_schema(value, schema, specification)


def test_original_tag_rejects_bool_revision_and_unregistered_extra_property(specification):
    schema = specification["components"]["schemas"]["Tag"]
    valid = {"id": str(uuid4()), "name": "标签", "group": "", "revision": 1, "state": "ENABLED"}
    validate_original_schema(valid, schema, specification)
    for invalid in (
        valid | {"revision": True},
        valid | {"new_unregistered_field": 1},
        valid | {"group": None},
        valid | {"id": "not-uuid"},
    ):
        with pytest.raises((AssertionError, ValueError)):
            validate_original_schema(invalid, schema, specification)
