# -*- coding:utf-8 -*-
import logging
from contextlib import asynccontextmanager
from typing import Optional, Iterable

import aiomysql

logger = logging.getLogger(__name__)


class AsyncMySQL:
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        database: str,
        port: int = 3306,
        charset: str = "utf8mb4",
        maxsize: int = 10,
        init_command: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self.maxsize = maxsize
        self.init_command = init_command
        self.pool: Optional[aiomysql.Pool] = None

    async def init_pool(self):
        if not self.pool:
            self.pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                charset=self.charset,
                maxsize=self.maxsize,
                autocommit=True,
                pool_recycle=600,
                init_command=self.init_command,
            )

    @asynccontextmanager
    async def get_cursor(self, as_dict: bool = False):
        cursor_type = aiomysql.DictCursor if as_dict else aiomysql.Cursor
        async with self.pool.acquire() as conn:
            async with conn.cursor(cursor_type) as cur:
                try:
                    yield cur
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"Database error: {e}")
                    raise
                else:
                    await conn.commit()

    async def fetchall(
        self, sql: str, params: Optional[Iterable] = None, as_dict: bool = False
    ):
        async with self.get_cursor(as_dict=as_dict) as cursor:
            await cursor.execute(sql, params or ())
            return await cursor.fetchall()

    async def fetchone(
        self, sql: str, params: Optional[Iterable] = None, as_dict: bool = False
    ):
        async with self.get_cursor(as_dict=as_dict) as cursor:
            await cursor.execute(sql, params or ())
            return await cursor.fetchone()

    async def execute(
        self, sql: str, params: Optional[Iterable] = None, as_dict: bool = False
    ):
        async with self.get_cursor(as_dict=as_dict) as cursor:
            await cursor.execute(sql, params or ())
            return cursor.rowcount

    @staticmethod
    def construct_insert_sql(table: str, columns: list):
        """生成插入SQL语句"""
        placeholders = ", ".join(["%s"] * len(columns))
        return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"

    @staticmethod
    def generate_insert_sql(table: str, data_dict: dict) -> tuple[str, list]:
        columns = ", ".join(data_dict.keys())
        placeholders = ", ".join(["%s"] * len(data_dict))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        return sql, list(data_dict.values())
