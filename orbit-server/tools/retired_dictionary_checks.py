"""真实数据库事务内验证字典退役；所有验收写入在 finally 中回滚，不创建广告。"""

import asyncio
import base64
import json
import os
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from orbit_api.channel_contract import parse_channel
from orbit_api.channel_store import ChannelStore
from orbit_api.credentials import CredentialCipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.launch_references import validate_sources
from orbit_api.reference_contract import parse_import
from orbit_api.reference_store import ReferenceStore


async def run(database_url, actor):
    engine = create_async_engine(database_url)
    tokens = DirectoryTokens(
        CredentialCipher("isolated", {"isolated": base64.b64encode(os.urandom(32)).decode()})
    )
    channels, references = ChannelStore(tokens), ReferenceStore(tokens)
    passed = []
    async with async_sessionmaker(engine)() as session:
        try:
            current = await channels.context(session, actor)
            caps = await channels.capabilities(session, actor, "")
            csrf = caps["csrf_token"]
            value = parse_channel(
                json.dumps(
                    {
                        "code": "retirement_" + uuid4().hex[:12],
                        "name": "回滚验收渠道",
                        "ownership": {
                            "owner_team_id": current.team_id,
                            "data_owner_user_ids": [current.subject_id],
                        },
                        "type": "WEBSITE",
                        "media": "META",
                        "url": "https://example.com/",
                        "status": "ENABLED",
                    }
                ).encode()
            )
            key = str(uuid4())
            saved = await channels.save(
                session, actor, "", csrf, key, value, None, None, str(uuid4())
            )
            assert not {"product_id", "agent_id"} & saved.keys()
            replay = await channels.save(
                session, actor, "", csrf, key, value, None, None, str(uuid4())
            )
            assert saved == replay
            params = {"tenant": current.tenant_id, "id": saved["id"]}
            sqlrow = (
                await session.execute(
                    text(
                        "SELECT product_id,agent_id FROM orbit_channel WHERE tenant_id=:tenant AND id=:id"
                    ),
                    params,
                )
            ).one()
            assert tuple(sqlrow) == (None, None)
            labels = await channels.display_labels(session, actor, [saved["id"]])
            assert labels["items"][0]["owners"][0]["id"] == current.subject_id
            assert (await channels.edit_context(session, actor, saved["id"])) == {"references": {}}
            passed.append("create/replay/labels without dictionaries")
            # 模拟历史JSON和产品锁：退役字段不泄漏，也不能阻止编辑。
            await session.execute(
                text(
                    "UPDATE orbit_channel SET value_json=JSON_SET(value_json,'$.product_id',:legacy,'$.agent_id',:legacy),product_locked=1 WHERE tenant_id=:tenant AND id=:id"
                ),
                params | {"legacy": str(uuid4())},
            )
            historical = await channels.get(session, actor, saved["id"])
            assert not {"product_id", "agent_id"} & historical.keys()
            saved = await channels.save(
                session,
                actor,
                "",
                csrf,
                str(uuid4()),
                value | {"name": "可编辑"},
                saved["id"],
                saved["revision"],
                str(uuid4()),
            )
            saved = await channels.save(
                session,
                actor,
                "",
                csrf,
                str(uuid4()),
                {"ownership": value["ownership"], "reason": "验收分配"},
                saved["id"],
                saved["revision"],
                str(uuid4()),
                "owners",
            )
            plan = {
                "ownership": {
                    "owner_user_id": current.subject_id,
                    "owner_team_id": current.team_id,
                },
                "account_ids": [],
                "asset_ids": [],
                "campaigns": [],
                "identity_bindings": [],
                "channel_id": saved["id"],
            }
            source = await validate_sources(session, current, plan, permission="launch.create")
            assert source["channel"]["id"] == saved["id"] and "channel_references" not in source
            passed.append("legacy edit/assignment/launch source")
            saved = await channels.save(
                session,
                actor,
                "",
                csrf,
                str(uuid4()),
                {"reason": "验收停用"},
                saved["id"],
                saved["revision"],
                str(uuid4()),
                "archive",
            )
            assert saved["status"] == "DISABLED"
            try:
                await validate_sources(session, current, plan, permission="launch.create")
                raise AssertionError("disabled channel accepted")
            except OrbitError as error:
                assert error.code == "CHANNEL_UNAVAILABLE"
            count = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM orbit_reference_event WHERE tenant_id=:tenant AND resource_id=:id"
                    ),
                    params,
                )
            ).scalar_one()
            assert count == 4
            passed.append("archive/launch rejection/atomic audit")
            rcaps = await references.capabilities(session, actor, "")
            vendor = {
                "id": str(uuid4()),
                "kind": "VENDOR",
                "name": "回滚验收户商",
                "source_key": uuid4().hex,
                "availability": "AVAILABLE",
                "owner_team_id": current.team_id,
                "data_owner_user_ids": [current.subject_id],
            }
            value = {
                "kind": "VENDOR",
                "source": "rollback-check",
                "reason": "退役回归验收",
                "base_catalog_revision": rcaps["catalog_revision"],
                "items": [vendor],
            }
            preview = await references.preview(
                session,
                actor,
                "",
                rcaps["csrf_token"],
                str(uuid4()),
                parse_import(json.dumps(value).encode()),
                str(uuid4()),
            )
            assert preview["state"] == "VALIDATED"
            committed = await references.commit(
                session,
                actor,
                "",
                rcaps["csrf_token"],
                str(uuid4()),
                preview["id"],
                preview["revision"],
                str(uuid4()),
            )
            assert committed["state"] == "COMMITTED"
            vendors = await references.list(session, actor, "VENDOR", {"page_size": 200})
            assert any(row["value"]["id"] == vendor["id"] for row in vendors["items"])
            passed.append("vendor preview/commit/list")
            for kind in ("PRODUCT", "BUSINESS_AGENT"):
                try:
                    await references.list(session, actor, kind, {"page_size": 20})
                    raise AssertionError("retired kind listed")
                except OrbitError as error:
                    assert error.code == "REFERENCE_KIND_RETIRED"
                await session.execute(
                    text(
                        "UPDATE orbit_reference_import SET input_json=JSON_SET(input_json,'$.kind',:kind),state='VALIDATED' WHERE tenant_id=:tenant AND id=:id"
                    ),
                    {"tenant": current.tenant_id, "id": preview["id"], "kind": kind},
                )
                try:
                    await references.commit(
                        session,
                        actor,
                        "",
                        rcaps["csrf_token"],
                        str(uuid4()),
                        preview["id"],
                        2,
                        str(uuid4()),
                    )
                    raise AssertionError("retired pending import committed")
                except OrbitError as error:
                    assert error.code == "REFERENCE_KIND_RETIRED"
            passed.append("retired lists and old pending imports blocked")
        finally:
            await session.rollback()
    async with engine.connect() as connection:
        assert not (
            await connection.execute(
                text("SELECT id FROM orbit_channel WHERE tenant_id=:tenant AND id=:id"), params
            )
        ).first()
    await engine.dispose()
    print(json.dumps({"passed": passed, "all_test_writes_rolled_back": True}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(
        run(
            os.environ["ORBIT_CHECK_DATABASE_URL"], int(os.environ.get("ORBIT_CHECK_ACTOR_ID", "1"))
        )
    )
