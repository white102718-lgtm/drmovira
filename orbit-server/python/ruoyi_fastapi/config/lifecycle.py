"""ORBIT框架启动只验证已审核结构，不隐式建表或更新用户数据库。"""

from typing import Literal

from sqlalchemy import inspect

from config.database import Base, DataSourceRegistry
from utils.log_util import logger


async def init_create_table(
    *, stage: Literal['platform', 'plugin_entities'] = 'platform', log_success_enabled: bool = True
) -> None:
    async with DataSourceRegistry.connection() as connection:
        names = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
        required = {table.name for table in Base.metadata.tables.values() if not table.info.get('plugin_artifact')}
        # ORBIT使用显式SQL迁移，不依赖原生ORM create_all或自动回填历史。
        required |= {
            'orbit_tenant',
            'orbit_user_scope',
            'orbit_business_user',
            'orbit_business_team',
            'orbit_business_team_manager',
            'orbit_system_configuration',
            'orbit_configuration_audit',
            'orbit_configuration_idempotency',
            'orbit_configuration_outbox',
            'orbit_directory_clock',
            'orbit_directory_idempotency',
            'orbit_directory_audit',
            'orbit_directory_outbox',
            'orbit_business_role',
            'orbit_business_role_menu',
            'orbit_business_role_action',
        }
        missing = sorted(required - names)
        if missing:
            raise RuntimeError('Python框架数据库尚未完成显式迁移：' + ','.join(missing))
        user_columns = await connection.run_sync(
            lambda sync: {column['name'] for column in inspect(sync).get_columns('orbit_business_user')}
        )
        if not {'display_name', 'invited', 'created_at', 'updated_at'}.issubset(user_columns):
            raise RuntimeError('Python人员目录尚未完成显式迁移006；未自动执行DDL')
    if log_success_enabled:
        logger.info('ORBIT Python框架结构检查通过；未执行建表或迁移')
