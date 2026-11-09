"""Python后台入口：复用真实RuoYi-FastAPI系统模块，新增ORBIT扩展。"""

from fastapi import FastAPI
from starlette.responses import JSONResponse

from orbit_api.login_adapter import LoginJsonAdapter


def configured_material_objects():
    """对象根只取可信ORBIT私有配置；无效配置不阻断原框架，文件操作明确503。"""
    from pathlib import Path

    from config.orbit_runtime import private_values

    from orbit_api.material_objects import LocalMaterialObjects

    root = private_values().get("ORBIT_PYTHON_MATERIAL_OBJECT_ROOT")
    if not isinstance(root, str) or not root.strip():
        return None
    try:
        return LocalMaterialObjects(Path(root))
    except (OSError, ValueError):
        return None


def create_app() -> FastAPI:
    """调用上游工厂；启动前需显式完成独立数据库初始化，不能自动迁移预览。"""
    from config.database import DataSourceRegistry
    from server import create_app as create_ruoyi
    from sqlalchemy import text

    app = create_ruoyi()
    from orbit_api.material_scanner_registry import MaterialScannerRegistry

    # 每个应用独立空注册表；受控启动所有者未发布实例时明确不可用。
    app.state.material_scanner_registry = MaterialScannerRegistry()
    # 权威预检来源只能由服务端显式接线；不从浏览器verified或任意版本字符串构造。
    app.state.launch_validation_provider = None
    app.state.launch_allocation_provider = None
    app.state.launch_execution_provider = None
    app.state.metric_profile_fixture_mode = False
    app.state.rule_editor_fixture = False
    from common.annotation.cache_annotation import ApiCache
    from common.directory_mutation_policy import DirectoryMutationPolicy
    from common.directory_policy import DirectoryReadPolicy

    from orbit_api.native_bulk_lifecycle import guard_native_bulk_lifecycle

    DirectoryMutationPolicy.register(guard_native_bulk_lifecycle)

    from orbit_api.native_directory import (
        describe_native_directory_object,
        guard_native_directory_object,
        native_cache_scope,
        native_directory_scope,
    )

    DirectoryReadPolicy.register(
        native_directory_scope, guard_native_directory_object, describe_native_directory_object
    )
    ApiCache.register_scope_resolver(native_cache_scope)
    from module_identity.service.identity_service import IdentitySecurityEventService

    from orbit_api.identity_guard import protect_business_identity_event

    IdentitySecurityEventService.register_business_guard(protect_business_identity_event)
    from module_admin.service.user_service import UserService

    from orbit_api.identity_guard import (
        business_contact_uniqueness_required,
        protect_business_profile_edit,
        protect_business_role_assignment,
    )

    UserService.register_business_edit_guard(protect_business_profile_edit)
    UserService.register_business_contact_policy(business_contact_uniqueness_required)
    UserService.register_business_role_guard(protect_business_role_assignment)
    from orbit_api.native_user_changes import capture_native_user_change, finish_native_user_change

    UserService.register_business_change_bridge(
        capture_native_user_change, finish_native_user_change
    )
    from module_admin.service.role_service import RoleService

    from orbit_api.role_bridge import reject_native_business_role_mutation

    RoleService.register_business_mutation_guard(reject_native_business_role_mutation)
    from module_admin.service.login_service import LoginService

    from orbit_api.native_session import (
        AuthSnapshotBoundary,
        enrich_native_token,
        validate_native_token,
    )

    LoginService.register_security_bridge(enrich_native_token, validate_native_token)
    from orbit_api.cookie_auth import has_cookie_session, resolve_cookie_user
    from orbit_api.cookie_identity import CookieIdentityBoundary

    LoginService.register_external_session(has_cookie_session, resolve_cookie_user)
    app.add_middleware(LoginJsonAdapter)
    from orbit_api.configuration_routes import router
    from orbit_api.http_boundary import OrbitApiBoundary, register_errors

    app.add_middleware(OrbitApiBoundary)
    app.add_middleware(AuthSnapshotBoundary)
    app.add_middleware(CookieIdentityBoundary)
    register_errors(app)
    app.include_router(router)
    from orbit_api.team_routes import router as team_router

    app.include_router(team_router)
    from orbit_api.execution_agent_routes import router as execution_agent_router
    from orbit_api.profile_binding_routes import router as profile_binding_router

    from orbit_api.agent_capability_routes import router as agent_capability_router

    app.include_router(agent_capability_router)
    app.include_router(execution_agent_router)
    app.include_router(profile_binding_router)
    from orbit_api.role_routes import router as role_router

    app.include_router(role_router)
    from orbit_api.user_routes import router as user_router

    app.include_router(user_router)
    from orbit_api.authentication_routes import router as authentication_router

    app.include_router(authentication_router)
    from orbit_api.invitation_routes import router as invitation_router

    app.include_router(invitation_router)
    from orbit_api.channel_routes import router as channel_router
    from orbit_api.reference_routes import router as reference_router
    from orbit_api.vendor_alias_routes import router as vendor_alias_router

    app.include_router(vendor_alias_router)
    app.include_router(reference_router)
    app.include_router(channel_router)
    from orbit_api.account_scope_routes import router as account_scope_router
    from orbit_api.launch_naming_routes import router as launch_naming_router
    from orbit_api.launch_routes import router as launch_router
    from orbit_api.template_recipient_routes import router as template_recipient_router
    from orbit_api.template_routes import router as template_router

    app.include_router(launch_router)
    app.include_router(launch_naming_router)
    from orbit_api.launch_validation_routes import router as launch_validation_router

    app.include_router(launch_validation_router)
    from orbit_api.launch_allocation_routes import router as launch_allocation_router

    app.include_router(launch_allocation_router)
    from orbit_api.launch_execution_routes import router as launch_execution_router

    app.include_router(launch_execution_router)
    from orbit_api.metric_profile_routes import router as metric_profile_router

    app.include_router(metric_profile_router)
    from orbit_api.metrics_routes import router as metrics_router

    app.include_router(metrics_router)
    from orbit_api.rule_display_metadata_routes import router as rule_display_metadata_router
    from orbit_api.rule_editor_definition_routes import router as rule_editor_definition_router
    from orbit_api.rule_editor_routes import router as rule_editor_router
    from orbit_api.rule_editor_scope_routes import router as rule_editor_scope_router
    from orbit_api.rule_list_filter_routes import router as rule_list_filter_router
    from orbit_api.rule_recovery_context_routes import router as rule_recovery_context_router
    from orbit_api.rule_routes import router as rule_router
    from orbit_api.rule_schedule_preview_routes import router as rule_schedule_preview_router
    from orbit_api.rule_scope_options_routes import router as rule_scope_options_router

    # 静态编辑入口先注册，避免被原 /{rule_id} 当作规则UUID。
    app.include_router(rule_editor_router)
    app.include_router(rule_editor_definition_router)
    app.include_router(rule_editor_scope_router)
    app.include_router(rule_schedule_preview_router)
    app.include_router(rule_scope_options_router)
    app.include_router(rule_display_metadata_router)
    app.include_router(rule_recovery_context_router)
    from orbit_api.account_channel_routes import router as account_channel_router

    app.include_router(account_channel_router)
    app.include_router(rule_list_filter_router)
    app.include_router(rule_router)
    app.include_router(template_recipient_router)
    app.include_router(template_router)
    from orbit_api.task_routes import router as task_router

    app.include_router(task_router)
    from orbit_api.task_event_routes import router as task_event_router

    app.include_router(task_event_router)
    app.include_router(account_scope_router)
    from orbit_api.cookie_auth import public_origin
    from orbit_api.material_routes import create_material_router
    from orbit_api.material_taxonomy_routes import router as material_taxonomy_router

    app.include_router(material_taxonomy_router)

    app.include_router(
        create_material_router(configured_material_objects(), origin_provider=public_origin)
    )
    from orbit_api.account_details_routes import router as account_details_router
    from orbit_api.account_routes import accounts_router
    from orbit_api.account_routes import router as account_import_router

    app.include_router(account_import_router)
    from orbit_api.account_identities_routes import router as account_identities_router

    app.include_router(account_identities_router)
    # extended固定路径必须先于原/{account_id}注册，原Account合同不变。
    app.include_router(account_details_router)
    from orbit_api.account_actions_routes import router as account_actions_router
    from orbit_api.account_assignment_options_routes import (
        router as account_assignment_options_router,
    )
    from orbit_api.account_command_routes import router as account_command_router

    app.include_router(account_assignment_options_router)
    app.include_router(account_actions_router)
    app.include_router(account_command_router)
    app.include_router(accounts_router)

    @app.get("/health/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        """实际检查数据库与缓存，不用固定成功冒充已启动；不返回连接细节。"""
        try:
            async with DataSourceRegistry.connection() as connection:
                await connection.execute(text("SELECT 1"))
            await app.state.redis.ping()
        except Exception:
            return JSONResponse({"status": "unavailable"}, 503)
        return JSONResponse({"status": "ready", "backend": "python", "database": "mysql"})

    return app
