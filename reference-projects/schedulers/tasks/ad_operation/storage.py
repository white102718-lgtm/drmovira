import datetime
import logging
from zoneinfo import ZoneInfo
from bson import ObjectId
from db.clients import mongo_client, mysql_client
from model_type_defs.ad_operation_type import OpType, OperationFields
from utils.common import LEVEL, RunStatus


def update_status(_id: str, status: RunStatus, error=None):
    update_data = {
        "status": status.value,
        "update_time": datetime.datetime.now(ZoneInfo("Asia/Shanghai")),
    }
    if error:
        update_data["error"] = error
    mongo_client["ad_operations"].update_one(
        {"_id": ObjectId(_id)},
        {"$set": update_data},
    )


def get_account_id_by_level(level: str, obj_id: str) -> str | None:
    """
    根据 level 和 id 从 Doris 查询 account_id
    """
    level_to_column = {
        LEVEL.ad.value: "ad_id",
        LEVEL.adset.value: "ad_set_id",
        LEVEL.campaign.value: "campaign_id",
    }
    column = level_to_column.get(level)
    sql = f"SELECT account_id FROM ad_daily_detail WHERE {column} = '{obj_id}' ORDER BY date DESC LIMIT 1"
    try:
        result = mysql_client.read(sql)
        if result and len(result) > 0:
            return result[0][0]
    except Exception as e:
        logging.error(f"查询 Doris 获取 account_id 失败{level},{obj_id}: {e}")
    return None


def get_token_by_app_id(app_id: str, proj: dict = None):
    if proj is None:
        proj = {"app_secret": 1, "proxy": 1, "_id": 0}
    return mongo_client["accounts"].find_one({"app_id": app_id}, projection=proj)


def get_dev_app_by_account_id(account_id: str) -> dict | None:
    """
    用 account_id 在 fb_system_users 里找到归属的系统用户（账户→开发者映射），
    再用其 _id 作为 app_id 取 accounts 中状态为启用(status=1)的开发者配置。
    活跃与否由 accounts.status 决定，不读 fb_system_users 自身的 status。
    """
    try:
        sys_users = list(
            mongo_client["fb_system_users"].find(
                {"accounts.id": account_id},
                {"_id": 1},
            )
        )
        if not sys_users:
            logging.warning(
                f"未找到包含 account_id={account_id} 的 fb_system_users 记录"
            )
            return None
        sys_user_ids = [u["_id"] for u in sys_users]
        matched_dev_info = mongo_client["accounts"].find_one(
            {"app_id": {"$in": sys_user_ids}, "status": 1},
            {"app_id": 1, "access_token": 1, "_id": 0, "app_secret": 1, "proxy": 1},
        )
        if matched_dev_info:
            return matched_dev_info
        logging.warning(f"未找到 app_id in {sys_user_ids} 的有效开发者配置")
    except Exception as e:
        logging.error(f"查询开发者信息失败: {e}")
    return None


def _persist_new(message: OperationFields, insert_data: dict, save_status: bool) -> None:
    """agent 上游：直接插入 mongo"""
    if not save_status:
        insert_data["status"] = RunStatus.FAILED.value
        mongo_client["ad_operations"].insert_one(insert_data)
        return
    insert_data["dev_app"] = message.get("dev_app")
    result = mongo_client["ad_operations"].insert_one(insert_data)
    message["_id"] = str(result.inserted_id)


def _persist_existing(message: OperationFields, save_status: bool, now) -> None:
    """系统接口上游：mongo 已有记录，按需更新"""
    if not save_status:
        update_status(message["_id"], RunStatus.FAILED)
        return
    mongo_client["ad_operations"].update_one(
        {"_id": ObjectId(message["_id"])},
        {"$set": {
            "status": RunStatus.STARTED,
            "dev_app": message.get("dev_app"),
            "data": message,
            "update_time": now,
        }},
    )


def save_message(message: OperationFields):
    now = datetime.datetime.now(ZoneInfo("Asia/Shanghai"))

    save_status = True
    insert_data = {
        "status": (
            RunStatus.STARTED.value
            if message.get("auto_run", False)
            else RunStatus.MANUAL.value
        ),
        "start_time": now,
        "update_time": now,
        "data": message,
    }
    if message["type"] == OpType.CREATE.value:
        account_ids = [
            item["account_id"]
            for item in message.get("create_config", [])
            if item.get("account_id")
        ]
        if not account_ids:
            save_status = False
    else:
        # 非创建操作：根据 level 和 id 查询 account_id，然后获取 dev_app
        level = message.get("level")
        obj_id = message.get("id")
        if level and obj_id and not message.get("dev_app"):
            account_id = get_account_id_by_level(level, obj_id)
            if account_id:
                dev_app = get_dev_app_by_account_id(account_id.removeprefix("act_"))
                if dev_app:
                    message["dev_app"] = dev_app
                    logging.info(
                        f"根据 {level}={obj_id} 找到 account_id={account_id}, app_id={dev_app.get('app_id')}"
                    )
                else:
                    logging.warning(
                        f"未找到 account_id={account_id} 对应的活跃系统开发者(accounts)"
                    )
                    save_status = False
            else:
                logging.warning(f"未找到 {level}={obj_id} 对应的 account_id")
                save_status = False

    if message.get("_id"):
        _persist_existing(message, save_status, now)
    else:
        _persist_new(message, insert_data, save_status)

    if not save_status:
        return None
    if message.get("auto_run", False):
        return message
    return None
