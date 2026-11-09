"""MD 开放接口客户端(开户/像素/绑包/主页/充值申请)。

认证: HMAC-SHA256, X-Sign = HmacSHA256(X-Timestamp + X-Nonce, SECRET_KEY) 十六进制小写。
五个接口 userId 都必传(query 参数), 服务端据此确定申请人/部门/租户。
所有申请提交后进入待审核状态。
"""
import hashlib
import hmac
import uuid
from datetime import datetime

import requests

# 生产; 测试环境: http://54.250.165.37:9998/admin-server
BASE_URL = "https://api.tango-game.com/admin-server"
SECRET_KEY = "REDACTED_REFERENCE_SECRET"
# 申请用户ID(sys_user.user_id; 暂用王子龙 122, tenant=1 与 md_account_opened 一致)
USER_ID = 122


def _post(path: str, body) -> dict:
    timestamp = str(int(datetime.now().timestamp() * 1000))
    nonce = str(uuid.uuid4())
    sign = hmac.new(
        SECRET_KEY.encode("utf-8"),
        (timestamp + nonce).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    resp = requests.post(
        BASE_URL + path,
        params={"userId": USER_ID},
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": "schedulers/1.0",
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Sign": sign,
        },
        json=body,
        timeout=15,
    )
    result = resp.json()
    if result.get("code") != 200:
        raise RuntimeError(f"{path} 失败: {result}")
    return result


def recharge_apply(account_opened_id: int, amount: float) -> dict:
    """已开账户充值申请。changeType 固定 1=充值。"""
    return _post(
        "/open/outsource/md/account/rechargeApply",
        {"accountOpenedId": account_opened_id, "amount": amount, "changeType": 1},
    )


def open_account_apply(channel_id: int, items: list[dict]) -> dict:
    """开户申请。items 元素必填: openAccountNum(不小于渠道最低购买数)/authType/authAccount;
    可选: accountName/rechargeAmount/amountType/timezone/remark。"""
    return _post(
        "/open/outsource/md/apply/openAccount",
        {"channelId": channel_id, "items": items},
    )


def pixel_apply(items: list[dict]) -> dict:
    """像素申请, 可一次多条。元素必填: bms/accountIds/channel(≤50字);
    可选: pixelNames/pixelIds。多值用分号分隔。"""
    return _post("/open/outsource/md/apply/pixel", items)


def bind_package_apply(items: list[dict]) -> dict:
    """绑包申请, 可一次多条。元素必填: accountIds(分号分隔)/appConfId(关联 fb_auth_conf.id);
    可选: bindAppLink。"""
    return _post("/open/outsource/md/apply/bindPackage", items)


def page_apply(items: list[dict]) -> dict:
    """主页申请, 可一次多条。元素必填: region/pageCount(≥1)/authBm。"""
    return _post("/open/outsource/md/apply/page", items)
