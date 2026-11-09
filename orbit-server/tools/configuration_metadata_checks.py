"""系统配置元数据真实HTTP专项；供完整回归和相关变更快速复验共同使用。"""

import uuid

CASES = [
    "pythonConfigurationMetadataContract",
    "pythonConfigurationMetadataRejectsIdentityAndPreservesErrorContract",
    "pythonConfigurationMetadataRevocationIsImmediate",
]


def run_configuration_metadata_checks(client, admin, headers, token, password, cases):
    path = "/api/v1/system-configurations/metadata"
    public = client.get(path, headers=headers)
    assert public.status_code == 200 and public.json()["encryptionReady"] is True
    sections = public.json()["sections"]
    assert len(sections) == 12
    original = [section for section in sections if section["key"] != "MATERIAL_SCANNER"]
    assert len(original) == 11
    assert sum(len(section["fields"]) for section in original) == 62
    scanner = [section for section in sections if section["key"] == "MATERIAL_SCANNER"]
    assert len(scanner) == 1 and len(scanner[0]["fields"]) == 1
    field = scanner[0]["fields"][0]
    assert field["key"] == "profileId" and field["type"] == "text"
    assert field["required"] is True and field["defaultValue"] == ""
    assert public.headers["cache-control"] == "no-store"
    uuid.UUID(public.headers["x-request-id"])
    assert "apiKey" in public.text and "jwt_secret" not in public.text
    cases.append("pythonConfigurationMetadataContract")
    for response, expected in [
        (client.get(path), 401),
        (client.get(path + "?tenant_id=forged", headers=headers), 400),
        (client.get(path, headers=headers | {"X-Target-Tenant": "forged"}), 403),
    ]:
        assert response.status_code == expected
        assert set(response.json()) == {"code", "message", "request_id"}
        assert response.json()["request_id"] == response.headers["x-request-id"]
        assert response.headers["cache-control"] == "no-store"
        assert token not in response.text and password not in response.text
    cases.append("pythonConfigurationMetadataRejectsIdentityAndPreservesErrorContract")
    with admin.cursor() as cursor:
        cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31081")
    try:
        revoked = client.get(path, headers=headers)
        assert revoked.status_code == 403
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status='0' WHERE menu_id=31081")
    assert client.get(path, headers=headers).status_code == 200
    cases.append("pythonConfigurationMetadataRevocationIsImmediate")
