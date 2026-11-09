from app.conf import DorisConf, ErpMySQLConf
from app.db.async_mysql import AsyncMySQL
from app.db.async_redis import get_redis_cli


doris_db = AsyncMySQL(
    DorisConf.HOST,
    DorisConf.USER,
    DorisConf.PASSWORD,
    "ad",
    DorisConf.PORT,
    maxsize=50,
    init_command="SET query_timeout = 60",
)
erp_db = AsyncMySQL(
    ErpMySQLConf.HOST,
    ErpMySQLConf.USER,
    ErpMySQLConf.PASSWORD,
    ErpMySQLConf.DATABASE,
    ErpMySQLConf.PORT,
)


async def get_db() -> AsyncMySQL:
    return doris_db


async def get_erp_db() -> AsyncMySQL:
    return erp_db


redis_cli = get_redis_cli(0)
redis_cli_1 = get_redis_cli(1)
redis_cli_2 = get_redis_cli(2)
redis_cli_3 = get_redis_cli(3)
