"""仅可见规则的有限展示投影；不借人员/团队目录动作，不新增来源锁。"""

from sqlalchemy import bindparam, text

from orbit_api.errors import OrbitError
from orbit_api.rule_access import (
    authorize_rule,
    require_rule_visible,
    revalidate_access,
    transaction,
)
from orbit_api.rule_contract import MAX_SAFE
from orbit_api.rule_display_metadata_contract import (
    created_at_text,
    metadata_response,
    parse_rule_ids,
    unavailable,
)
from orbit_api.rule_store import RuleStore


class RuleDisplayMetadataStore:
    async def get(self, session, actor, rule_ids):
        transaction(session)
        # 即使被内部直接调用也不能绕过CSV结构/唯一/上限。
        if type(rule_ids) is not tuple or any(type(value) is not str for value in rule_ids):
            raise ValueError("RULE_METADATA_PARSED_IDS_REQUIRED")
        ids = parse_rule_ids(",".join(rule_ids))
        access = await authorize_rule(session, actor, "rules.read")
        await RuleStore(None)._clock(session, access)
        query = text(
            "SELECT h.*,v.payload_json,v.payload_hash,v.metric_profile_version,"
            "v.metric_profile_hash,v.profile_proof_hash FROM orbit_rule_head h "
            "JOIN orbit_rule_version v ON v.tenant_id=h.tenant_id AND v.rule_id=h.id "
            "AND v.revision=h.revision WHERE h.tenant_id=:tenant AND h.id IN :ids "
            "ORDER BY h.id FOR SHARE OF h,v"
        ).bindparams(bindparam("ids", expanding=True))
        found = (
            (await session.execute(query, {"tenant": access.current.tenant_id, "ids": ids}))
            .mappings()
            .all()
        )
        by_id = {}
        for row in found:
            require_rule_visible(access, row)
            if row["id"] in by_id:
                unavailable()
            if type(row["created_by"]) is not int or not 1 <= row["created_by"] <= MAX_SAFE:
                unavailable()
            created_at_text(row["created_at"])
            RuleStore.public(row)  # 原Rule完整payload/hash/归属/字段结构核验，不替代成只读ID。
            by_id[row["id"]] = row
        if set(by_id) != set(ids):
            raise OrbitError(404, "NOT_FOUND", "规则不存在或不在当前可读范围")
        owners = tuple(sorted({row["owner_user_id"] for row in found}))
        teams = tuple(sorted({row["owner_team_id"] for row in found}))
        creators = tuple(sorted({row["created_by"] for row in found}))
        names_sql = text(
            "SELECT CONVERT('OWNER' USING utf8mb4) COLLATE utf8mb4_0900_as_cs AS resource_kind,"
            "CONVERT(b.id USING utf8mb4) COLLATE utf8mb4_0900_as_cs AS ref_id,"
            "CONVERT(b.display_name USING utf8mb4) COLLATE utf8mb4_0900_as_cs AS label "
            "FROM orbit_business_user b WHERE b.tenant_id=:tenant AND b.id IN :owners "
            "UNION ALL SELECT CONVERT('CREATOR' USING utf8mb4) COLLATE utf8mb4_0900_as_cs,"
            "CAST(b.user_id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_0900_as_cs,"
            "CONVERT(b.display_name USING utf8mb4) COLLATE utf8mb4_0900_as_cs "
            "FROM orbit_business_user b WHERE b.tenant_id=:tenant AND b.user_id IN :creators "
            "UNION ALL SELECT CONVERT('TEAM' USING utf8mb4) COLLATE utf8mb4_0900_as_cs,"
            "CONVERT(t.id USING utf8mb4) COLLATE utf8mb4_0900_as_cs,"
            "CONVERT(t.name USING utf8mb4) COLLATE utf8mb4_0900_as_cs "
            "FROM orbit_business_team t "
            "WHERE t.tenant_id=:tenant AND t.id IN :teams"
        ).bindparams(*(bindparam(key, expanding=True) for key in ("owners", "creators", "teams")))
        rows = (
            (
                await session.execute(
                    names_sql,
                    {
                        "tenant": access.current.tenant_id,
                        "owners": owners,
                        "creators": creators,
                        "teams": teams,
                    },
                )
            )
            .mappings()
            .all()
        )
        labels = {}
        allowed = {
            "OWNER": set(owners),
            "TEAM": set(teams),
            "CREATOR": {str(value) for value in creators},
        }
        for row in rows:
            kind, reference = row["resource_kind"], row["ref_id"]
            key = (kind, reference)
            if kind not in allowed or reference not in allowed[kind] or key in labels:
                unavailable()
            labels[key] = row["label"]
        items = [
            {
                "rule_id": rule_id,
                "revision": by_id[rule_id]["revision"],
                "owner_user_name": labels.get(("OWNER", by_id[rule_id]["owner_user_id"])),
                "owner_team_name": labels.get(("TEAM", by_id[rule_id]["owner_team_id"])),
                "created_by": by_id[rule_id]["created_by"],
                "created_by_name": labels.get(("CREATOR", str(by_id[rule_id]["created_by"]))),
                "created_at": created_at_text(by_id[rule_id]["created_at"]),
            }
            for rule_id in ids
        ]
        response = metadata_response(items)
        await revalidate_access(session, access)
        return response
