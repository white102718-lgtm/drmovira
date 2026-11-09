"""账户只读目录：按当前归属和实时动作求交集，稳定UUID续页，不做深OFFSET。"""



from orbit_api.account_metadata import timezone_payload, unknown_observation
from orbit_api.configuration_store import _decode


class AccountStore:
    def __init__(self, tokens):
        self.tokens = tokens

    @staticmethod
    def public(row, now):
        saved = _decode(row["value_json"])
        value = {
            "vendor_alias": saved.get("vendor_alias"),
            "spend": saved.get("spend", unknown_observation(row["currency"], kind="SPEND")),
            "balance": saved.get("balance", unknown_observation(row["currency"])),
        }
        # 当前归属由可索引列控制；不能让旧JSON快照扩大当前投手的数据范围。
        value.update(
            {
                "id": row["id"],
                "external_id": row["external_id"],
                "name": row["name"],
                "ownership": {
                    "owner_user_id": row["owner_user_id"],
                    "owner_team_id": row["owner_team_id"],
                },
                "vendor_id": row["vendor_id"],
                "currency": row["currency"],
                "auth_status": row["auth_status"],
                "account_status": row["account_status"],
                "revision": row["revision"],
                "timezone": timezone_payload(row["timezone_id"], now),
                "synced_at": row["synced_at"].isoformat(timespec="milliseconds") + "Z"
                if row["synced_at"]
                else None,
            }
        )
        return value

    async def get(self, session, actor, identifier, *, details=False):
        # 保留原14字段Account合同，观测值与18列扩展共用同一次范围/日期查询。
        from orbit_api.account_details_contract import filters
        from orbit_api.account_details_store import AccountDetailsStore

        result = await AccountDetailsStore(self.tokens).list(
            session, actor, filters({}), identifier=identifier
        )
        value = result["items"][0]
        return value if details else value["account"]

    async def list(self, session, actor, filters, cursor=None):
        from orbit_api.account_details_store import AccountDetailsStore

        # 旧接口不增加响应属性，旧用途签名仍隔离，绑定同一观测水位防跨页混读。
        query = {"mode": "TODAY", **filters}
        result = await AccountDetailsStore(self.tokens).list(
            session, actor, query, cursor, purpose="ACCOUNT_CURSOR_V1"
        )
        return {
            "items": [value["account"] for value in result["items"]],
            "next_cursor": result["next_cursor"],
            "data_as_of": result["data_as_of"],
            "scope_version": result["scope_version"],
        }
