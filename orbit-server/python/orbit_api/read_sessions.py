"""跨来源预读使用独占READ COMMITTED连接，避免旧RR快照与新clock混合。

隔离级别在连接首次SQL之前设置；连接归还时由SQLAlchemy恢复引擎默认值。
保留框架会话类、认证缓存及静默SQL设置，不修改全局引擎或连接池配置。
"""

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine

from orbit_api.errors import OrbitError


@asynccontextmanager
async def read_committed_session(registry):
    """由调用方显式开启业务事务；会话和连接的生命周期均限于本次请求。"""
    async with registry.session(log_sql=False) as template:
        engine = template.bind
        if not isinstance(engine, AsyncEngine):
            raise TypeError("当前读取要求框架异步引擎")
        async with engine.connect() as connection:
            try:
                await connection.execution_options(isolation_level="READ COMMITTED")
                async with type(template)(
                    bind=connection,
                    sync_session_class=type(template.sync_session),
                    autoflush=template.autoflush,
                    expire_on_commit=False,
                    info=dict(template.info),
                ) as session:
                    yield session
            except BaseException as exc:
                # 失败连接不回池复用，尤其不能通过重新连接来“恢复”原物理连接。
                if not isinstance(exc, OrbitError) and not connection.invalidated:
                    await connection.invalidate()
                raise
