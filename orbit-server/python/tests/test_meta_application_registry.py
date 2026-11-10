import json

import pytest

from orbit_api.configuration import metadata, parse_write
from orbit_api.errors import OrbitError


def test_meta_application_binding_has_login_config_and_separate_marketing_token():
    fields = next(s for s in metadata() if s["key"] == "META_APP")["fields"]
    by_key = {f["key"]: f for f in fields}
    assert "loginConfigId" in by_key
    assert by_key["marketingToken"]["type"] == "secret"
    data = dict(
        section="META_APP",
        name="广告应用",
        enabled=True,
        settings={"appId": "123", "graphVersion": "v24.0", "loginConfigId": "456"},
        secrets={
            "appSecret": {"operation": "REPLACE", "value": "secret"},
            "marketingToken": {"operation": "REPLACE", "value": "token"},
        },
        reason="绑定应用",
    )
    assert parse_write(json.dumps(data).encode()).settings["loginConfigId"] == "456"
    data["settings"]["loginConfigId"] = "invalid"
    with pytest.raises(OrbitError):
        parse_write(json.dumps(data).encode())


def test_selected_application_identity_is_part_of_authorization_fingerprint():
    from orbit_api.meta_connection_contract import MetaApplication

    app = MetaApplication("123", "secret", "v24.0", "456")
    assert hasattr(app, "configuration_id")
    assert hasattr(app, "configuration_revision")


@pytest.mark.asyncio
async def test_registry_rejects_disabled_or_changed_configuration():
    from orbit_api import meta_connection_contract as contract

    assert hasattr(contract, "application_from_configuration")

    class Cipher:
        def decrypt_internal(self, envelope, tenant, identifier, slot):
            assert (tenant, identifier, slot) == ("tenant", "config", "appSecret")
            return "private-secret"

    row = dict(
        id="config",
        tenant_id="tenant",
        section="META_APP",
        enabled=1,
        revision=2,
        settings_json={"appId": "123", "graphVersion": "v24.0", "loginConfigId": "456"},
        secrets_json={"appSecret": "encrypted", "marketingToken": "not-used"},
    )
    app = contract.application_from_configuration(row, Cipher(), expected_revision=2)
    assert app.configuration_id == "config"
    assert app.app_id == "123"
    assert "private-secret" not in repr(app)
    for bad in [row | {"enabled": 0}, row | {"section": "META_BM"}, row | {"revision": 3}]:
        with pytest.raises(OrbitError):
            contract.application_from_configuration(bad, Cipher(), expected_revision=2)


def test_tenant_managed_application_revocation_namespace_is_not_global_app_id():
    from orbit_api.meta_connection_contract import MetaApplication

    a = MetaApplication("123", "secret", "v24.0", "456", "tenant-a-config", 1)
    b = MetaApplication("123", "other-secret", "v24.0", "456", "tenant-b-config", 1)
    assert hasattr(a, "principal_namespace")
    assert a.principal_namespace != b.principal_namespace
    assert a.principal_namespace != "123"
