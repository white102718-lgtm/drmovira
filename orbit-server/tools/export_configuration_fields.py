"""从已编译的Java字段白名单导出新增系统配置字段，不复制猜测字段规则。"""

import argparse
import csv
import io
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", required=True, help="Java21可执行文件绝对路径")
    args = parser.parse_args()
    result = subprocess.run([args.java, "-cp", str(ROOT / "ruoyi-system/target/classes"), str(ROOT / "tools/ExportConfigurationFields.java")],
                            check=True, capture_output=True)
    fields = []
    for values in csv.reader(io.StringIO(result.stdout.decode("utf-8")), delimiter="\t"):
        section, section_label, key, label, kind, required, default, minimum, maximum, options = values
        fields.append({"section": section, "section_label": section_label, "key": key, "label": label,
                       "type": kind, "required_when_enabled": required == "true",
                       "default": None if default == "null" else int(default) if kind == "integer" else default,
                       "minimum": None if minimum == "null" else int(minimum),
                       "maximum": None if maximum == "null" else int(maximum),
                       "options": options.split("|") if options else [],
                       "logic": "密钥只写不读；KEEP保持/REPLACE认证加密/CLEAR明确清除；不回显、不缓存、不记录原文" if kind == "secret" else "白名单、类型、Unicode/长度/范围校验；启用时条件必填；保存增版本并重置只读验证"})
    if not fields:
        raise RuntimeError("Java字段目录导出为空，拒绝生成遗漏字段的台账")
    for field in fields:
        if field['section'] == 'AI_SUGGESTIONS' and field['key'] == 'minimumCooldownMinutes':
            field['logic'] = '全局分析冷却下限0至10080分钟，默认60；与规则冷却取较大值，按规则+对象限制；保存才生成新版本，执行器原子生效待实现'
        if field['section'] == 'AI_SUGGESTIONS' and field['key'] == 'maximumDailyAnalysesPerObject':
            field['logic'] = '每规则每对象调度当地日分析上限1至1000，默认5；与规则日额度取较小值；不按页面人数计数，执行器原子生效待实现'
    destination = ROOT / "docs/orbit/extensions/configuration-fields.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(fields, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_openapi(fields, destination.parent)
    print(json.dumps({"fields": len(fields), "path": str(destination)}, ensure_ascii=True))


def write_openapi(fields, directory):
    """为用户新增配置能力独立导出契约，不改写产品原127路径合同。"""
    sections = sorted({field["section"] for field in fields})
    writes = []
    secret_change = {"type": "object", "additionalProperties": False,
                     "required": ["operation"], "properties": {
                         "operation": {"type": "string", "enum": ["KEEP", "REPLACE", "CLEAR"]},
                         "value": {"type": ["string", "null"], "maxLength": 8192}}}
    for section in sections:
        properties = {}
        secret_properties = {}
        for field in (field for field in fields if field["section"] == section):
            if field["type"] == "secret":
                secret_properties[field["key"]] = {"$ref": "#/components/schemas/SecretChange"}
                continue
            rule = {"type": "integer" if field["type"] == "integer" else "string", "description": field["label"]}
            if field["default"] is not None:
                rule["default"] = field["default"]
            if field["type"] == "integer":
                rule.update(minimum=field["minimum"], maximum=field["maximum"])
            else:
                rule["maxLength"] = field["maximum"] or 500
            if field["options"]:
                rule["enum"] = field["options"]
            properties[field["key"]] = rule
        writes.append({"type": "object", "additionalProperties": False,
                       "required": ["section", "name", "enabled", "settings", "reason"], "properties": {
                           "section": {"type": "string", "const": section},
                           "name": {"type": "string", "minLength": 1, "maxLength": 100},
                           "enabled": {"type": "boolean"},
                           "settings": {"type": "object", "additionalProperties": False, "properties": properties},
                           "secrets": {"type": "object", "additionalProperties": False, "properties": secret_properties},
                           "reason": {"type": "string", "minLength": 1, "maxLength": 500}}})
    response = {"description": "脱敏结果；只读测试与配置启用均不代表广告写能力已验证"}
    idem = {"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string", "pattern": "^[A-Za-z0-9:_-]{8,128}$"}}
    revision = {"name": "If-Match", "in": "header", "required": True, "schema": {"type": "string", "pattern": '^"[1-9][0-9]{0,17}"$'}}
    identity = {"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}
    body = {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ConfigurationWrite"}}}}
    # 只读测试人工原因是1.1已实现的契约，重新导出字段时必须保留。
    test_body = {
        "required": True,
        "content": {"application/json": {"schema": {
            "type": "object", "additionalProperties": False, "required": ["reason"],
            "properties": {"reason": {
                "type": "string", "minLength": 1, "maxLength": 500,
                "description": "人工测试原因；NFC与trim后非空，禁止控制字符，不填写凭据"
            }}
        }}}
    }
    contract = {"openapi": "3.1.0", "info": {"title": "ORBIT新增系统配置接口", "version": "1.2.0"},
                "security": [{"ruoyiBearer": []}], "paths": {
                    "/api/v1/system-configurations": {
                        "get": {"operationId": "listSystemConfigurations", "responses": {"200": response}},
                        "post": {"operationId": "createSystemConfiguration", "parameters": [idem], "requestBody": body, "responses": {"201": response}}},
                    "/api/v1/system-configurations/metadata": {
                        "get": {"operationId": "getSystemConfigurationMetadata", "responses": {"200": response}}},
                    "/api/v1/system-configurations/{id}": {
                        "get": {"operationId": "getSystemConfiguration", "parameters": [identity], "responses": {"200": response}},
                        "put": {"operationId": "updateSystemConfiguration", "parameters": [identity, revision, idem], "requestBody": body, "responses": {"200": response}}},
                    "/api/v1/system-configurations/{id}/test": {
                        "post": {"operationId": "testSystemConfigurationReadOnly", "parameters": [identity, revision], "requestBody": test_body, "responses": {"200": response}}}},
                "components": {"securitySchemes": {"ruoyiBearer": {"type": "http", "scheme": "bearer"}},
                               "schemas": {"SecretChange": secret_change, "ConfigurationWrite": {"oneOf": writes}}},
                "x-business-validation": "服务端另校验启用条件必填、凭据状态、同租户AI引用、角色/菜单/动作、版本、幂等与风险收紧限制；错误码400/403/404/409/422/500。只读测试不调用生成或广告写入。"}
    contract["x-authentication-response"] = {"status": 401, "code": "UNAUTHENTICATED", "cacheControl": "no-store", "scope": "仅新增系统配置路径使用独立安全链；若依原接口保持原行为；Token会话存储仍需真实Redis联调"}
    contract["paths"]["/api/v1/system-configurations/{id}/history"] = {"get": {
        "operationId": "listSystemConfigurationHistory", "parameters": [identity,
            {"name": "beforeRevision", "in": "query", "schema": {"type": "integer", "minimum": 1}},
            {"name": "pageSize", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}}]}}
    schemas = contract["components"]["schemas"]
    schemas["AuditPage"] = {"type": "object", "required": ["items", "nextBeforeRevision"], "properties": {
        "nextBeforeRevision": {"type": ["integer", "null"]}, "items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "properties": {
                "id": {"type": "string"}, "actorId": {"type": "integer"}, "action": {"type": "string"},
                "revision": {"type": "integer"},
                "beforeRevision": {"type": ["integer", "null"], "minimum": 0},
                "beforeHash": {"type": ["string", "null"], "pattern": "^[a-f0-9]{64}$"},
                "afterHash": {"type": ["string", "null"], "pattern": "^[a-f0-9]{64}$"},
                "hashAlgorithm": {"type": ["string", "null"], "enum": ["SHA256_STATE_V1", None]},
                "changedFields": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"}, "createdAt": {"type": "string", "format": "date-time"}}}}}}

    schemas["SecretState"] = {"type": "object", "additionalProperties": False, "required": ["configured", "hint"],
                              "properties": {"configured": {"type": "boolean"}, "hint": {"type": "string"}}}
    schemas["ConfigurationView"] = {"type": "object", "additionalProperties": False,
                                    "required": ["id", "section", "name", "enabled", "revision", "settings", "secrets", "verificationStatus", "verifiedAt", "updatedAt"],
                                    "properties": {
                                        "id": {"type": "string", "format": "uuid"}, "section": {"type": "string", "enum": sections},
                                        "name": {"type": "string"}, "enabled": {"type": "boolean"}, "revision": {"type": "integer", "minimum": 1},
                                        "settings": {"type": "object", "additionalProperties": {"type": ["string", "integer"]}},
                                        "secrets": {"type": "object", "additionalProperties": {"$ref": "#/components/schemas/SecretState"}},
                                        "verificationStatus": {"type": "string", "enum": ["UNTESTED", "READ_VERIFIED", "FAILED", "BLOCKED"]},
                                        "verifiedAt": {"type": ["string", "null"], "format": "date-time"},
                                        "updatedAt": {"type": "string", "format": "date-time"}}}
    schemas["Error"] = {"type": "object", "additionalProperties": False, "required": ["code", "message", "request_id"],
                        "properties": {"code": {"type": "string"}, "message": {"type": "string"}, "request_id": {"type": "string", "format": "uuid"}}}
    schemas["Metadata"] = {"type": "object", "required": ["sections", "encryptionReady"], "properties": {
        "encryptionReady": {"type": "boolean"}, "sections": {"type": "array", "items": {"type": "object",
            "required": ["key", "label", "fields"], "properties": {"key": {"type": "string"}, "label": {"type": "string"},
            "fields": {"type": "array", "items": {"type": "object", "properties": {
                "key": {"type": "string"}, "label": {"type": "string"}, "type": {"type": "string", "enum": ["text", "integer", "select", "secret"]},
                "required": {"type": "boolean"}, "defaultValue": {"type": ["string", "integer", "null"]},
                "minimum": {"type": ["integer", "null"]}, "maximum": {"type": ["integer", "null"]},
                "options": {"type": "array", "items": {"type": "string"}}}}}}}}}}
    schemas["ProbeResponse"] = {"type": "object", "required": ["configuration", "result"], "properties": {
        "configuration": {"$ref": "#/components/schemas/ConfigurationView"},
        "result": {"type": "object", "required": ["status", "message"], "properties": {
            "status": {"type": "string", "enum": ["READ_VERIFIED", "FAILED", "BLOCKED"]}, "message": {"type": "string"}}}}}
    for path, path_item in contract["paths"].items():
        for method, operation in path_item.items():
            schema = {"$ref": "#/components/schemas/ConfigurationView"}
            if path.endswith("/metadata"):
                schema = {"$ref": "#/components/schemas/Metadata"}
            elif path.endswith("/history"):
                schema = {"$ref": "#/components/schemas/AuditPage"}
            elif path.endswith("/test"):
                schema = {"$ref": "#/components/schemas/ProbeResponse"}
            elif path == "/api/v1/system-configurations" and method == "get":
                schema = {"type": "array", "items": schema}
            code = "201" if operation["operationId"] == "createSystemConfiguration" else "200"
            operation["responses"] = {code: {"description": response["description"], "content": {"application/json": {"schema": schema}}},
                                      "default": {"description": "安全脱敏错误，真实HTTP状态400/403/404/409/422/500", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}}}
    (directory / "system-configurations.openapi.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
