"""原目录批量写入的可选宿主边界；独立框架保持原技术账户流程。"""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession


class DirectoryMutationPolicy:
    _guards: tuple[Callable[[AsyncSession, str, list], Awaitable[None]], ...] = ()

    @classmethod
    def register(cls, guard: Callable[[AsyncSession, str, list], Awaitable[None]]) -> None:
        if guard not in cls._guards:
            cls._guards += (guard,)

    @classmethod
    async def guard(cls, session: AsyncSession, operation: str, identifiers: list) -> None:
        """所有宿主预检必须在首笔DAO写入前完成，拒绝时不能留下半批结果。"""
        for guard in cls._guards:
            await guard(session, operation, identifiers)
