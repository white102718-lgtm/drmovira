# -*- coding:utf-8 -*-
import threading
import logging
from urllib.parse import quote_plus
from functools import wraps

import pandas as pd
import pymysql


class LazyImport:
    def __init__(self, module_name):
        self.module_name = module_name
        self.module = None

    def __getattr__(self, name):
        if self.module is None:
            self.module = __import__(self.module_name)
        return getattr(self.module, name)


mutex = threading.Lock()


def reconnect(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        mutex.acquire()
        try:
            self.conn.ping(reconnect=True)
            result = func(self, *args, **kwargs)
            return result
        finally:
            mutex.release()

    return wrapper


def with_transaction(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            result = func(self, *args, **kwargs)
            return result
        except Exception as e:
            self.conn.rollback()
            logging.error(f"执行SQL失败，已回滚: {e}")
            raise

    return wrapper


class Mysql:
    def __init__(self, host, user, password, database, port, charset="utf8mb4"):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._charset = charset
        self._conn = None
        self._cursor = None
        self._engine = None

    def __del__(self):
        if self._cursor is not None:
            self._cursor.close()
        if self._conn is not None:
            self._conn.close()
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
    def conn(self):
        if self._conn is None:
            self._conn = pymysql.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
                charset=self._charset,
                autocommit=True,
            )
        return self._conn

    @property
    def cursor(self):
        if self._cursor is None:
            self._cursor = self.conn.cursor()
        return self._cursor

    @reconnect
    def read(self, sql):
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    @reconnect
    @with_transaction
    def execute(self, sql):
        return self.cursor.execute(sql)

    @reconnect
    @with_transaction
    def execute_many(self, sql, data):
        return self.cursor.executemany(sql, data)

    def read_df(self, sql):
        return pd.read_sql(sql, self.engine)

    def write_df(self, df: pd.DataFrame, table: str):
        df.to_sql(table, self.engine, if_exists="append", index=False)

    @staticmethod
    def construct_insert_sql(table, columns):
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({('%s, ' * len(columns))[:-2]})"
        return sql
