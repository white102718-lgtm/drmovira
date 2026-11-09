"""投放草稿仅冻结可信身份引用；不签发预检能力、执行授权或环境绑定。"""

from orbit_api.errors import OrbitError
from orbit_api.identity_publication_readmodel import IdentityPublicationReadmodel
from orbit_api.identity_publication_store import lock_sources
from orbit_api.launch_access import digest
from orbit_api.meta_observation_registry import one


async def prepare_identity_sources(session, current, bindings):
    """先发现全部来源再按release排序锁定；来源探测绝不替代后续当前权限核验。"""
    probes = {}
    for identifier in sorted({row["account_id"] for row in bindings}):
        probes[identifier] = await one(
            session,
            "SELECT p.evidence_id,p.release_id FROM orbit_account_identity_head h "
            "JOIN orbit_account_identity_history v ON v.tenant_id=h.tenant_id "
            "AND v.account_id=h.account_id AND v.revision=h.revision "
            "JOIN orbit_identity_publication_provenance p ON p.tenant_id=v.tenant_id "
            "AND p.evidence_id=v.evidence_id WHERE h.tenant_id=:tenant AND h.account_id=:account",
            {"tenant": current.tenant_id, "account": identifier},
        )
    sources = {}
    for release_id in sorted({p["release_id"] for p in probes.values() if p is not None}):
        sources[release_id] = await lock_sources(session, current, release_id)
    return {
        identifier: {
            "probe": dict(probe) if probe is not None else None,
            "configurations": sources[probe["release_id"]][0] if probe is not None else [],
            "release": sources[probe["release_id"]][1] if probe is not None else None,
        }
        for identifier, probe in probes.items()
    }


def validate_identity_resources(value, binding, index, inventory):
    """缺省草稿字段可继续补齐；已填写的身份资源必须属于该账户当前可信库存。"""
    root = f"/identity_bindings/{index}"

    def invalid(path, message):
        raise OrbitError(422, "LAUNCH_IDENTITY_UNAVAILABLE", message, root + path)

    if inventory["account_id"] != binding["account_id"]:
        invalid("/account_id", "身份库存不属于当前账户")
    usable = {
        (row["kind"], row["external_id"]) for row in inventory["resources"] if row["usable"] is True
    }

    def resource(kind, identifier, path):
        if identifier is not None and (kind, identifier) not in usable:
            invalid(path, "身份资源不在该账户当前可用库存中，请刷新身份后重新选择")

    resource("PAGE", binding["page_id"], "/page_id")
    objectives = {
        group["local_id"]: campaign.get("objective")
        for campaign in value["campaigns"]
        for group in campaign["adsets"]
    }
    for i, group in enumerate(binding["groups"]):
        path = f"/groups/{i}"
        website = bool(group["pixel_id"] or group["conversion_event"])
        application = bool(group["application_id"] or group["object_store_url"])
        if website and application:
            invalid(path, "网站与应用身份字段不能混用")
        objective = objectives.get(group["adset_local_id"])
        if (objective == "OUTCOME_SALES" and application) or (
            objective == "OUTCOME_APP_PROMOTION" and website
        ):
            invalid(path, "身份字段与当前广告系列目标不一致")
        resource("PIXEL", group["pixel_id"], path + "/pixel_id")
        resource("APPLICATION", group["application_id"], path + "/application_id")
    for i, override in enumerate(binding["ad_overrides"]):
        resource("PAGE", override["page_id"], f"/ad_overrides/{i}/page_id")


async def resolve_identity_dependencies(session, current, value, prepared):
    """范围解析后必须再次核账户成员资格，不能让跨页快照绕过身份账户交集。"""
    for index, binding in enumerate(value["identity_bindings"]):
        if binding["account_id"] not in value["account_ids"]:
            raise OrbitError(
                422,
                "FIELD_VALIDATION_FAILED",
                "身份账户必须属于已解析的账户范围",
                f"/identity_bindings/{index}/account_id",
            )
    result = {}
    reader = IdentityPublicationReadmodel()
    for index, binding in sorted(
        enumerate(value["identity_bindings"]), key=lambda item: item[1]["account_id"]
    ):
        identifier = binding["account_id"]
        source = prepared[identifier]
        inventory = await reader.get(session, current.actor_id, identifier, prepared_sources=source)
        validate_identity_resources(value, binding, index, inventory)
        # 来源版本/哈希仅证明草稿引用时库存；优化事件/商店域/执行能力仍须正式预检。
        result[identifier] = {
            "evidence_id": source["probe"]["evidence_id"],
            "release_id": source["probe"]["release_id"],
            "capability_version": inventory["capability_version"],
            "observed_at": inventory["observed_at"],
            "inventory_hash": digest(inventory),
        }
    return {"identities": result} if result else {}
