# -*- coding:utf-8 -*-
import logging
from contextlib import contextmanager
from urllib.parse import quote_plus

import pymysql


class LazyImport:
    def __init__(self, module_name):
        self.module_name = module_name
        self.module = None

    def __getattr__(self, name):
        if self.module is None:
            self.module = __import__(self.module_name)
        return getattr(self.module, name)


class Mysql:
    def __init__(self, host, user, password, database, port, charset="utf8mb4",
                 pool_size=0, setsession=None):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._charset = charset
        self._engine = None
        # 0 = 不池化(每次新建/关闭,保持老行为);>0 = 进程内连接数硬上限,借满阻塞等待
        self._pool_size = pool_size
        # 每条物理连接创建时跑一次的 SQL(如 Doris 的 SET session 变量),断线重连自动重跑
        self._setsession = setsession
        self._pool = None

    def __del__(self):
        if self._engine is not None:
            self._engine.dispose()

    @property
    def engine(self):
        if self._engine is None:
            create_engine = LazyImport("sqlalchemy").create_engine
            charset = f"?charset={self._charset}" if self._charset else ""
            self._engine = create_engine(
                f"mysql+pymysql://{self._user}:REDACTED_REFERENCE_SECRET@"
                f"{self._host}:{self._port}/{self._database}{charset}",
            )
        return self._engine

    @property
    def _conn_pool(self):
        if self._pool is None:
            from dbutils.pooled_db import PooledDB
            self._pool = PooledDB(
                creator=pymysql,
                maxconnections=self._pool_size,
                blocking=True,   # 借满则阻塞等待,自动节流,不会新建超额连接
                ping=1,          # 取连接前 ping,绕开被服务端掐断的死连接
                setsession=self._setsession,
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
                charset=self._charset,
                autocommit=True,
                connect_timeout=30,
            )
        return self._pool

    def _connect(self):
        if self._pool_size:
            return self._conn_pool.connection()  # 池化连接:close() = 还池,非真关
        return pymysql.connect(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            database=self._database,
            charset=self._charset,
            autocommit=True,
            connect_timeout=30
        )

    @contextmanager
    def session(self):
        """单连接 + 单 cursor,让一次业务调用里的多条 SQL 共用一个连接,
        避免每条 SQL 都新建/断开。退出 with 自动关连接。

        典型用法(write_to_doris 等多 SQL 操作):
            with mysql_client.session() as cur:
                cur.execute("SET ...")
                cur.execute("SET ...")
                cur.executemany(insert_sql, rows)

        ⚠️ session 级变量必须用这个,不要用裸 execute()。
        Doris 的 `SET enable_unique_key_partial_update = true` /
        `SET enable_insert_strict = false` 等是 session 变量,
        必须跟后续 INSERT 共用同一连接才生效。
        裸 mysql_client.execute() 每次新建/关闭连接,SET 会落在一条
        session 上而 INSERT 跑在另一条,partial update 模式不生效 →
        INSERT 退化成普通 UPSERT 把未在列表里的列覆盖成 NULL。
        """
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                yield cursor
        finally:
            conn.close()

    def read(self, sql):
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall()
        finally:
            conn.close()

    def execute(self, sql):
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                try:
                    result = cursor.execute(sql)
                    conn.commit()
                    return result
                except Exception as e:
                    logging.error(f"执行SQL失败 {e}")
                    conn.rollback()
                    logging.error(f"已回滚: {e}")
                    raise
        finally:
            conn.close()

    def execute_many(self, sql, data):
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                try:
                    result = cursor.executemany(sql, data)
                    conn.commit()
                    return result
                except Exception as e:
                    logging.error(f"执行SQL失败 {e}")
                    conn.rollback()
                    logging.error(f"已回滚: {e}")
                    raise
        finally:
            conn.close()

    def read_df(self, sql):
        import pandas as pd
        with self.engine.connect() as conn:
            return pd.read_sql(sql, conn)

    def write_df(self, df, table: str):
        with self.engine.connect() as conn:
            df.to_sql(table, conn, if_exists="append", index=False)
            conn.commit()

    @staticmethod
    def construct_insert_sql(table, columns):
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({('%s, ' * len(columns))[:-2]})"
        return sql
