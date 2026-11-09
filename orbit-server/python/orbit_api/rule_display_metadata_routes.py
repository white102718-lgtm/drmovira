"""规则展示元数据批量GET；须先于原/{rule_id}注册。"""

import json
from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from sqlalchemy.exc import DBAPIError

from orbit_api.configuration_routes import _read_boundary
from orbit_api.errors import OrbitError
from orbit_api.rule_display_metadata_contract import RuleDisplayMetadataPage, parse_rule_ids
from orbit_api.rule_display_metadata_store import RuleDisplayMetadataStore

router = APIRouter(prefix="/api/v1/rules", tags=["ORBIT规则展示元数据"])
User = Annotated[CurrentUserModel, CurrentUserDependency()]


async def metadata_boundary(request):
    _read_boundary(request, {"rule_ids"})
    async for chunk in request.stream():
        if chunk:
            raise OrbitError(400, "INVALID_STRUCTURE", "规则展示元数据GET不接受正文")
    return parse_rule_ids(request.query_params.get("rule_ids"))


@router.get("/display-metadata", response_model=RuleDisplayMetadataPage)
async def display_metadata(request: Request, user: User):
    ids = await metadata_boundary(request)
    try:
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await RuleDisplayMetadataStore().get(session, user.user.user_id, ids)
    except OrbitError:
        raise
    except Exception as error:
        # 固定分类/errno/自有模块行号；绝不打印异常msg/SQL/params/Token。
        category = (
            "DBAPIError"
            if isinstance(error, DBAPIError)
            else "TypeError"
            if isinstance(error, TypeError)
            else "KeyError"
            if isinstance(error, KeyError)
            else "OTHER"
        )
        args = getattr(getattr(error, "orig", None), "args", ())
        errno = args[0] if args and type(args[0]) is int else None
        own_line = None
        current = error.__traceback__
        while current is not None:
            if current.tb_frame.f_code.co_filename.replace("\\", "/").endswith(
                "/rule_display_metadata_store.py"
            ):
                own_line = current.tb_lineno
            current = current.tb_next
        print(
            json.dumps(
                {
                    "scope": "rule-display-metadata",
                    "phase": "unexpected",
                    "category": category,
                    "errno": errno,
                    "store_line": own_line,
                }
            ),
            flush=True,
        )
        raise
