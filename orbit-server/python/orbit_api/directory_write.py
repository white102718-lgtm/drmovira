"""组织目录业务写入的共同提交尾部；调用方必须先获得目录锁并完成授权/CAS。"""

import hashlib
from uuid import uuid4

from sqlalchemy import text

from orbit_api.configuration_store import MAX_REVISION
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError


def public_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest() if value else None


async def append_directory_change(
    session,
    context,
    key,
    digest,
    before,
    after,
    fields,
    request_id,
    resource_type,
    *,
    record_idempotency=True,
):
    if resource_type not in {"TEAM", "ROLE", "USER"}:
        raise ValueError("未知目录类型")
    params = {
        "tenant": context.tenant_id,
        "actor": context.actor_id,
        "key": key,
        "hash": digest,
        "id": after["id"],
        "event": str(uuid4()),
        "revision": after["revision"],
        "before_revision": before["revision"] if before else 0,
        "before_hash": public_hash(before),
        "after_hash": public_hash(after),
        "fields": canonical(
            [field for field in fields if before is None or before[field] != after[field]]
        ),
        "action": "UPDATE" if before else "CREATE",
        "subject": context.subject_id,
        "team": context.team_id,
        "request": request_id,
        "response": canonical(after),
        "type": resource_type,
    }
    await session.execute(
        text("""
        INSERT INTO orbit_directory_audit
        (id,tenant_id,resource_type,resource_id,action,revision,before_revision,before_hash,after_hash,
         changed_fields_json,actor_id,actor_subject_id,actor_team_id,request_id,created_at)
        VALUES(:event,:tenant,:type,:id,:action,:revision,:before_revision,:before_hash,:after_hash,
         :fields,:actor,:subject,:team,:request,UTC_TIMESTAMP(3))
    """),
        params,
    )
    await session.execute(
        text("""
        INSERT INTO orbit_directory_outbox
        (event_id,tenant_id,resource_type,resource_id,revision,created_at)
        VALUES(:event,:tenant,:type,:id,:revision,UTC_TIMESTAMP(3))
    """),
        params,
    )
    if record_idempotency:
        await session.execute(
            text("""
        INSERT INTO orbit_directory_idempotency
        (tenant_id,actor_id,request_key,payload_hash,response_json)
        VALUES(:tenant,:actor,:key,:hash,:response)
        """),
            params,
        )
    updated = await session.execute(
        text("""
        UPDATE orbit_directory_clock SET revision=revision+1,updated_at=UTC_TIMESTAMP(3)
        WHERE tenant_id=:tenant AND revision<:maximum
    """),
        {**params, "maximum": MAX_REVISION},
    )
    if updated.rowcount != 1:
        raise OrbitError(409, "REVISION_EXHAUSTED", "目录版本已达上限")
