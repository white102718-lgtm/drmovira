from fastapi import APIRouter, Depends
from app.api.routes import (
    materials,
    tags,
    dashboard,
    dashboard_detail,
    dashboard_overview,
    developer,
    menu,
    user,
    platform_config,
    department,
    superset,
    creative,
    tg_config,
    operation,
    facebook_auth,
    fb_resource,
    ad_create_templates,
    material_category,
    material_groups,
    field_map,
    tg_webhook,
    oauth_client,
    material_orders,
    material_folders,
    material_common,
    material_dashboard,
    tasks,
    ad_config,
)
from app.core.security import auth_current_user

api_router = APIRouter(dependencies=[Depends(auth_current_user)])

# 需要注册的所有 router 模块
routers = [
    materials.router,
    tags.router,
    tags.router_edit,
    dashboard.router,
    dashboard_detail.router,
    dashboard_overview.router,
    developer.router,
    menu.router,
    user.router,
    user.role_router,
    user.auth_router,
    oauth_client.router,
    platform_config.router,
    material_category.router,
    material_groups.router,
    department.router,
    superset.router,
    creative.router,
    tg_config.router,
    operation.router,
    facebook_auth.router,
    fb_resource.router,
    ad_create_templates.router,
    field_map.router,
    tg_webhook.router,
    material_orders.router,
    material_folders.router,
    material_common.router,
    material_dashboard.router,
    tasks.router,
    ad_config.router,
]

# 循环注册
for r in routers:
    api_router.include_router(r)
