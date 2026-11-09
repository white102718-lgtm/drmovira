"""可选宿主目录读取边界；独立使用原框架时不附加业务条件。"""

from collections.abc import Awaitable, Callable

from sqlalchemy import ColumnElement, and_, true
from sqlalchemy.ext.asyncio import AsyncSession


class DirectoryReadPolicy:
    _scopes: tuple[Callable[[AsyncSession, str], Awaitable[ColumnElement]], ...] = ()
    _objects: tuple[Callable[[AsyncSession, str, int], Awaitable[None]], ...] = ()
    _metadata: tuple[Callable[[AsyncSession, str, int], Awaitable[dict]], ...] = ()

    @classmethod
    def register(
        cls,
        scope: Callable[[AsyncSession, str], Awaitable[ColumnElement]],
        guard: Callable[[AsyncSession, str, int], Awaitable[None]],
        metadata: Callable[[AsyncSession, str, int], Awaitable[dict]] | None = None,
    ) -> None:
        if scope not in cls._scopes:
            cls._scopes += (scope,)
        if guard not in cls._objects:
            cls._objects += (guard,)
        if metadata is not None and metadata not in cls._metadata:
            cls._metadata += (metadata,)

    @classmethod
    async def describe(cls, session: AsyncSession, kind: str, identifier: int) -> dict:
        """已通过对象读取校验后的只读界面提示；不得用于写入授权。"""
        result = {}
        for resolver in cls._metadata:
            result.update(await resolver(session, kind, identifier))
        return result

    @classmethod
    async def scope(cls, session: AsyncSession, kind: str) -> ColumnElement:
        """调用方必须在COUNT和分页前与原数据权限相交，不能对已分页结果后过滤。"""
        return and_(true(), *[await resolver(session, kind) for resolver in cls._scopes])

    @classmethod
    async def guard(cls, session: AsyncSession, kind: str, identifier: int) -> None:
        for guard in cls._objects:
            await guard(session, kind, identifier)
