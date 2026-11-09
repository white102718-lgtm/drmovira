"""标签分类独立能力合同；精确动作、不借素材读取、主体恢复边界。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError

TENANT = str(UUID(int=12))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["READ", "CREATE", "EDIT", "ARCHIVE"])
async def test_exact_taxonomy_action_without_assets_read(monkeypatch, operation):
    from orbit_api import material_taxonomy_capabilities as module

    context = BusinessContext(3, TENANT, "USER", str(UUID(int=13)), str(UUID(int=14)))
    authorize = AsyncMock(return_value=context)
    monkeypatch.setattr(module, "require_business_access", authorize)
    issued = []

    class Tokens:
        def session_binding(self, authorization, actor, tenant):
            assert (authorization, actor, tenant) == ("Bearer fixture", 3, TENANT)
            return "binding"

        def issue(self, purpose, claims):
            issued.append((purpose, claims))
            return "fixture-csrf-with-original-session"

    result = await module.current_taxonomy_capabilities(
        SimpleNamespace(in_transaction=lambda: True), 3, "Bearer fixture", operation, Tokens()
    )
    assert result == {
        "actor_id": 3,
        "tenant_id": TENANT,
        "csrf_token": None if operation == "READ" else "fixture-csrf-with-original-session",
    }
    assert len(authorize.await_args_list) == 2
    assert all(
        call.args[2:] == ("assets", "tags." + operation.lower())
        for call in authorize.await_args_list
    )
    assert len(issued) == (0 if operation == "READ" else 1)
    if issued:
        assert issued == [("DIRECTORY_CSRF_V1", {"binding": "binding"})]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", [None, "", "read", "DELETE", 1, True])
async def test_unknown_operation_rejected_before_authorization(monkeypatch, operation):
    from orbit_api import material_taxonomy_capabilities as module

    authorize = AsyncMock()
    monkeypatch.setattr(module, "require_business_access", authorize)
    with pytest.raises(OrbitError) as caught:
        await module.current_taxonomy_capabilities(
            SimpleNamespace(in_transaction=lambda: True), 3, "", operation, None
        )
    assert (caught.value.status, caught.value.pointer) == (422, "/operation")
    authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_requires_outer_transaction(monkeypatch):
    from orbit_api import material_taxonomy_capabilities as module

    authorize = AsyncMock()
    monkeypatch.setattr(module, "require_business_access", authorize)
    with pytest.raises(ValueError, match="TAXONOMY_TRANSACTION_REQUIRED"):
        await module.current_taxonomy_capabilities(
            SimpleNamespace(in_transaction=lambda: False), 3, "", "READ", None
        )
    authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_revocation_before_return_rejects(monkeypatch):
    from orbit_api import material_taxonomy_capabilities as module

    context = BusinessContext(3, TENANT, "USER", str(UUID(int=13)), str(UUID(int=14)))
    monkeypatch.setattr(
        module,
        "require_business_access",
        AsyncMock(side_effect=[context, OrbitError(403, "PERMISSION_DENIED", "revoked")]),
    )
    with pytest.raises(OrbitError) as caught:
        await module.current_taxonomy_capabilities(
            SimpleNamespace(in_transaction=lambda: True), 3, "", "READ", None
        )
    assert caught.value.status == 403


@pytest.mark.asyncio
async def test_changed_principal_cannot_return_initial_identity(monkeypatch):
    from orbit_api import material_taxonomy_capabilities as module

    context = BusinessContext(3, TENANT, "USER", str(UUID(int=13)), str(UUID(int=14)))
    changed = BusinessContext(3, str(UUID(int=99)), "USER", str(UUID(int=13)), str(UUID(int=14)))
    monkeypatch.setattr(
        module, "require_business_access", AsyncMock(side_effect=[context, changed])
    )
    with pytest.raises(OrbitError) as caught:
        await module.current_taxonomy_capabilities(
            SimpleNamespace(in_transaction=lambda: True), 3, "", "READ", None
        )
    assert caught.value.status == 403


@pytest.mark.parametrize(
    "change",
    [
        {"actor_id": True},
        {"actor_id": 0},
        {"actor_id": "3"},
        {"actor_id": 9007199254740992},
        {"tenant_id": "bad"},
        {"tenant_id": TENANT.upper().replace("c", "C") + " "},
        {"csrf_token": ""},
        {"csrf_token": "x" * 256},
        {"extra": True},
    ],
)
def test_strict_response_identity_and_csrf(change):
    from pydantic import ValidationError

    from orbit_api.material_taxonomy_capabilities import TaxonomyCapabilities

    with pytest.raises(ValidationError):
        TaxonomyCapabilities.model_validate(
            {"actor_id": 3, "tenant_id": TENANT, "csrf_token": None} | change
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,body,status",
    [
        (b"", b"", 422),
        (b"operation=DELETE", b"", 422),
        (b"operation=CREATE&operation=READ", b"", 400),
        (b"operation=CREATE&tenant_id=x", b"", 400),
        (b"operation=READ", b"{}", 400),
    ],
)
async def test_route_boundary_before_session(monkeypatch, query, body, status):
    import importlib.util
    import sys
    from pathlib import Path
    from types import ModuleType

    from fastapi import Depends
    from pydantic import BaseModel
    from starlette.requests import Request

    async def dep():
        pass

    def boundary(request, allowed):
        assert allowed == {"operation"}
        if set(request.query_params) - allowed:
            raise OrbitError(400, "UNKNOWN_FIELD", "unknown")
        if any(len(request.query_params.getlist(k)) != 1 for k in request.query_params):
            raise OrbitError(400, "INVALID_STRUCTURE", "duplicate")
        if "x-target-tenant" in request.headers:
            raise OrbitError(403, "PERMISSION_DENIED", "tenant")

    modules = {
        "common.aspect.pre_auth": {"CurrentUserDependency": lambda: Depends(dep)},
        "config.database": {"DataSourceRegistry": SimpleNamespace()},
        "module_admin.entity.vo.user_vo": {"CurrentUserModel": BaseModel},
        "orbit_api.configuration_routes": {
            "_read_boundary": boundary,
            "credential_cipher": lambda: pytest.fail("unexpected cipher"),
        },
    }
    for name, values in modules.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(__file__).resolve().parents[1] / "orbit_api/material_taxonomy_routes.py"
    spec = importlib.util.spec_from_file_location("pure_taxonomy_routes", path)
    routes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routes)

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/material-taxonomy/capabilities",
            "query_string": query,
            "headers": [],
        },
        receive,
    )
    with pytest.raises(OrbitError) as caught:
        await routes.capabilities(request, SimpleNamespace())
    assert caught.value.status == status
