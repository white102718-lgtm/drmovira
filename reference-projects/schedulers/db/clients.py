from datetime import timezone, timedelta

import pymongo
from bson.codec_options import CodecOptions

from conf import DorisConf, ErpMySQLConf
from conf import MongodbConf
from env_vault.env_conf import MongodbConfNew
from db.mysql import Mysql
from db.redis_client import REDIS_DB0_POOL_SIZE, get_redis_cli

mysql_client = Mysql(
    DorisConf.HOST, DorisConf.USER, DorisConf.PASSWORD, "ad", DorisConf.PORT,
    charset="", pool_size=10,  # 单进程 Doris 连接硬上限;多进程合计须 < Doris user max_connections(500)
    setsession=[
        "SET enable_unique_key_partial_update = true",
        "SET enable_insert_strict = false",
    ],
)

erp_db = Mysql(
    ErpMySQLConf.HOST,
    ErpMySQLConf.USER,
    ErpMySQLConf.PASSWORD,
    ErpMySQLConf.DATABASE,
    ErpMySQLConf.PORT,
)

redis_cli = get_redis_cli(0, max_connections=REDIS_DB0_POOL_SIZE)
redis_cli_1 = get_redis_cli(1)
redis_cli_2 = get_redis_cli(2)
redis_cli_3 = get_redis_cli(3)
client = pymongo.MongoClient(MongodbConf.CONNECTION)

tz_cst = timezone(timedelta(hours=8))
codec_options = CodecOptions(tz_aware=True, tzinfo=tz_cst)
mongo_client = client.get_database("plat", codec_options=codec_options)
mongo_client_user = client.get_database("user", codec_options=codec_options)

client_new = pymongo.MongoClient(MongodbConfNew.CONNECTION)
mongo_client_new = client_new.get_database("plat", codec_options=codec_options)
