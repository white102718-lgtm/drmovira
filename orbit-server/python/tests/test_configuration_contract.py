"""系统配置11类64字段合同及凭据操作，逐边界验证Python实现。"""

import json
from pathlib import Path

import pytest

from orbit_api.configuration import metadata, parse_probe_reason, parse_write
from orbit_api.errors import OrbitError


def body(section="AI_GPT", *, enabled=False):
    return {
        "section": section,
        "name": "测试配置",
        "enabled": enabled,
        "settings": {},
        "secrets": {},
        "reason": "首次配置",
    }


def parse(value):
    return parse_write(json.dumps(value, ensure_ascii=False).encode())


@pytest.mark.parametrize(
    "raw,status",
    [
        (b"", 400),
        (b"{}", 400),
        (b'{"reason":1}', 400),
        (b'{"reason":"a","extra":"b"}', 400),
        (b'{"reason":"a","reason":"b"}', 400),
        (b'{"reason":""}', 422),
        (b'{"reason":"x\\n"}', 422),
    ],
)
def test_probe_requires_unique_safe_human_reason(raw, status):
    with pytest.raises(OrbitError) as error:
        parse_probe_reason(raw)
    assert error.value.status == status


def test_probe_reason_normalizes_nfc_and_limits_unicode_codepoints():
    assert parse_probe_reason(json.dumps({"reason": " Cafe\u0301 "}).encode()) == "Café"
    assert len(parse_probe_reason(json.dumps({"reason": "😀" * 500}).encode())) == 500
    with pytest.raises(OrbitError):
        parse_probe_reason(json.dumps({"reason": "😀" * 501}).encode())


def test_ai_strategy_provider_reference_is_a_canonical_business_uuid():
    value = body("AI_SUGGESTIONS")
    value["settings"] = {"providerConfigId": "not-a-uuid"}
    with pytest.raises(OrbitError) as error:
        parse(value)
    assert error.value.pointer == "/settings/providerConfigId"
    assert error.value.status == 422
    value["settings"]["providerConfigId"] = "ABCDEF00-0000-0000-0000-000000000001"
    assert parse(value).settings["providerConfigId"] == "abcdef00-0000-0000-0000-000000000001"


def test_python_catalog_matches_all_original_extension_fields_without_java_runtime():
    source = Path(__file__).parents[2] / "docs/orbit/extensions/configuration-fields.json"
    original = json.loads(source.read_text(encoding="utf-8"))
    fields = [
        (section["key"], field)
        for section in metadata()
        if section["key"] != "MATERIAL_SCANNER"
        for field in section["fields"]
    ]
    assert len(fields) == len(original) == 64
    assert len(metadata()) == 12
    extension = [s for s in metadata() if s["key"] == "MATERIAL_SCANNER"]
    assert len(extension) == 1 and [f["key"] for f in extension[0]["fields"]] == ["profileId"]
    for (section, field), expected in zip(fields, original, strict=True):
        assert section == expected["section"]
        assert field == {
            "key": expected["key"],
            "label": expected["label"],
            "type": expected["type"],
            "required": expected["required_when_enabled"],
            "defaultValue": expected["default"],
            "minimum": expected["minimum"],
            "maximum": expected["maximum"],
            "options": expected["options"],
        }
    returned = metadata()
    returned[0]["fields"].clear()
    assert metadata()[0]["fields"]


@pytest.mark.parametrize("section", [m["key"] for m in metadata()])
def test_all_disabled_sections_have_valid_public_defaults(section):
    parsed = parse(body(section))
    assert parsed.section == section
    assert not parsed.enabled
    assert not set(parsed.settings).intersection(parsed.secrets)


def test_model_names_unicode_codepoints_nfc_and_control_characters():
    value = body()
    value["settings"] = {"model": "  Cafe\u0301 "}
    assert parse(value).settings["model"] == "Café"
    value["name"] = "😀" * 100
    assert parse(value).name == "😀" * 100
    value["name"] += "😀"
    with pytest.raises(OrbitError):
        parse(value)
    for invalid in ("model\n", "\tmodel", "model\u2028", "bad\ud800", "model\u202e", "\u200bmodel"):
        value = body()
        value["settings"] = {"model": invalid}
        # 单独surrogate不能UTF-8编码；JSON转义输入必须仍被拒绝。
        with pytest.raises(OrbitError):
            parse_write(json.dumps(value).encode())


@pytest.mark.parametrize("field", ["section", "name", "enabled", "settings", "secrets", "reason"])
def test_missing_required_root_field_is_structure_error(field):
    value = body()
    value.pop(field)
    with pytest.raises(OrbitError) as error:
        parse(value)
    assert error.value.status == 400


@pytest.mark.parametrize("invalid", [True, [], {}, None, 1.5])
def test_invalid_setting_pointer_identifies_real_property(invalid):
    value = body()
    value["settings"] = {"model": invalid}
    with pytest.raises(OrbitError) as error:
        parse(value)
    assert error.value.status == 400
    assert error.value.pointer == "/settings/model"


@pytest.mark.parametrize(
    "extra", ["tenant_id", "actor_id", "revision", "verificationStatus", "unknown"]
)
def test_cannot_inject_server_fields(extra):
    value = body()
    value[extra] = "forged"
    with pytest.raises(OrbitError) as error:
        parse(value)
    assert error.value.code == "UNKNOWN_FIELD"


def test_public_secret_positions_unknown_nested_fields_and_duplicate_json_rejected():
    for settings, secrets in [
        ({"apiKey": "fixture-key"}, {}),
        ({}, {"model": {"operation": "KEEP"}}),
        ({"unknown": 1}, {}),
    ]:
        value = body()
        value.update(settings=settings, secrets=secrets)
        with pytest.raises(OrbitError) as error:
            parse(value)
        assert error.value.status == 400
        assert "fixture-key" not in str(error.value)
    raw = json.dumps(body()).replace(
        '"settings": {}', '"settings": {"model":"first","model":"second"}'
    )
    with pytest.raises(OrbitError) as error:
        parse_write(raw.encode())
    assert error.value.code == "INVALID_STRUCTURE"


def test_every_integer_boundary_and_enum_are_checked():
    for section in metadata():
        for field in section["fields"]:
            if field["type"] == "integer":
                for accepted in (field["minimum"], field["maximum"]):
                    value = body(section["key"])
                    value["settings"][field["key"]] = accepted
                    assert parse(value).settings[field["key"]] == accepted
                for rejected in (field["minimum"] - 1, field["maximum"] + 1, True, "1", 1.5):
                    value = body(section["key"])
                    value["settings"][field["key"]] = rejected
                    with pytest.raises(OrbitError):
                        parse(value)
            elif field["type"] == "select":
                value = body(section["key"])
                value["settings"][field["key"]] = "UNSUPPORTED"
                with pytest.raises(OrbitError):
                    parse(value)


def test_enabled_condition_required_model_long_meta_ids_and_claude_date():
    value = body(enabled=True)
    with pytest.raises(OrbitError):
        parse(value)
    value["settings"]["model"] = "chosen-model"
    assert parse(value).settings["model"] == "chosen-model"
    value = body("META_BM", enabled=True)
    value["settings"] = {"businessId": "0" * 64, "graphVersion": "v22.0"}
    assert parse(value).settings["businessId"] == "0" * 64
    value["settings"]["businessId"] = "1" * 65
    with pytest.raises(OrbitError):
        parse(value)
    value = body("AI_CLAUDE")
    value["settings"]["apiVersion"] = "2026-02-30"
    with pytest.raises(OrbitError):
        parse(value)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://u:p@example.com",
        "https://example.com/#secret",
        "https://example.com:99999",
        "https:///missing",
    ],
)
def test_integration_url_syntax_is_https_without_credentials_or_fragment(url):
    value = body("NOTIFICATIONS")
    value["settings"]["webhookUrl"] = url
    with pytest.raises(OrbitError):
        parse(value)


def test_webhook_condition_and_secret_operations_never_disclose_values():
    value = body("NOTIFICATIONS", enabled=True)
    value["settings"]["channel"] = "WEBHOOK"
    with pytest.raises(OrbitError) as error:
        parse(value)
    assert error.value.code == "WEBHOOK_REQUIRED"
    for operation in ("KEEP", "CLEAR", "REPLACE"):
        value = body()
        change = {"operation": operation}
        if operation == "REPLACE":
            change["value"] = "fixture-key"
        value["secrets"]["apiKey"] = change
        parsed = parse(value)
        assert "fixture-key" not in repr(parsed)
        assert "fixture-key" not in parsed.model_dump_json()
    for change in [
        {"operation": "REPLACE"},
        {"operation": "KEEP", "value": "fixture-key"},
        {"operation": "CLEAR", "value": "fixture-key"},
        {"operation": "REPLACE", "value": "x" * 8193},
        {"operation": "REPLACE", "value": "key\n"},
    ]:
        value = body()
        value["secrets"]["apiKey"] = change
        with pytest.raises(OrbitError) as error:
            parse(value)
        assert "fixture-key" not in str(error.value)
