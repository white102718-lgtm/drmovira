"""仅13306/UUID库的预检协议Provider；没有真实平台authority，不可用于生产。

读取本轮实际Plan/Allocation/Name与目录水位，不调用平台，不执行广告。
名称以ORBIT_VALIDATION_FIXTURE_开头的计划才允许进入专属协议。
"""

import asyncio
import json
import re
from pathlib import Path
from time import monotonic

from sqlalchemy import text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.launch_validation_store import (
    ObservationReference,
    ValidationAuthorityProvider,
    ValidationEvidence,
    ValidationIssue,
)
from orbit_api.reference_access import scope_version

PREFIX = "ORBIT_VALIDATION_FIXTURE_"
CONTROL_ROOT = Path(__file__).resolve().parents[1] / ".runtime" / "launch-validation-control"


def control_directory(database, override=None):
    if not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database):
        raise ValueError("握手仅允许本轮UUID库")
    path = (
        Path(override)
        if override is not None
        else CONTROL_ROOT / ("run-" + database.removeprefix("orbit_py_it_"))
    )
    if path.parent != CONTROL_ROOT or not re.fullmatch(r"run-[a-f0-9]{32}", path.name):
        raise ValueError("握手目录必须位于专属固定根")
    for item in (CONTROL_ROOT.parent, CONTROL_ROOT, path):
        if item.is_symlink() or item.is_junction():
            raise ValueError("握手目录禁止符号链接")
    path.mkdir(parents=True, exist_ok=True)
    return path


async def guard(session):
    url = session.bind.url
    database = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
    if (
        url.host != "127.0.0.1"
        or url.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise OrbitError(
            503, "LAUNCH_VALIDATION_AUTHORITY_UNAVAILABLE", "专属协议禁止用于业务数据库"
        )
    return database


async def first(session, sql, values):
    return (await session.execute(text(sql), values)).mappings().first()


class IsolatedValidationProvider(ValidationAuthorityProvider):
    kind = "ISOLATED_TEST"

    def __init__(self, session_factory, control_dir=None):
        self.session_factory = session_factory
        self.control_dir = control_dir

    async def capture(self, value):
        plan, request = value.source.payload(), value.request()
        if not plan["name"].startswith(PREFIX):
            raise OrbitError(
                503, "LAUNCH_VALIDATION_AUTHORITY_UNAVAILABLE", "非本轮协议计划不可使用fixture"
            )
        async with self.session_factory() as session, session.begin():
            database = await guard(session)
            scope = await scope_version(session, value.current)
            params = {
                "tenant": value.current.tenant_id,
                "allocation": request["allocation_id"],
                "names": request["name_reservation_id"],
            }
            allocation = await first(
                session,
                "SELECT "
                """
                id, plan_id, plan_revision, state, task_id, algorithm_version, seed,
                input_hash, warnings_json
                """
                " FROM orbit_launch_allocation WHERE tenant_id=:tenant AND id=:allocation",
                params,
            )
            names = await first(
                session,
                "SELECT id,plan_id,plan_revision,naming_date FROM orbit_launch_name_reservation "
                "WHERE tenant_id=:tenant AND id=:names",
                params,
            )
            if allocation is None or names is None:
                raise OrbitError(404, "NOT_FOUND", "本轮协议来源不存在")
            if (
                allocation["plan_id"] != value.source.plan_id
                or names["plan_id"] != value.source.plan_id
            ):
                raise OrbitError(404, "NOT_FOUND", "协议引用不属于当前计划")
            if (
                allocation["plan_revision"] != value.source.source_revision
                or names["plan_revision"] != value.source.source_revision
            ):
                raise OrbitError(409, "STALE_PREVIEW", "实际协议引用配置源已变化")
            allocation = dict(allocation)
            warnings = allocation.pop("warnings_json")
            allocation["warnings"] = json.loads(warnings) if isinstance(warnings, str) else warnings
            allocation["items"] = [
                dict(row)
                for row in (
                    await session.execute(
                        text(
                            "SELECT slot_key,account_id,asset_id,asset_revision FROM "
                            "orbit_launch_allocation_item WHERE tenant_id=:tenant AND "
                            "allocation_id=:allocation ORDER BY ordinal LIMIT 10001"
                        ),
                        params,
                    )
                )
                .mappings()
                .all()
            ]
            names = dict(names)
            names.pop("plan_id")
            names["naming_date"] = names["naming_date"].isoformat()
            names["items"] = [
                {
                    "slot_key": row["slot_key"],
                    "name": row["name"],
                    "sequence": str(int(row["sequence"])),
                }
                for row in (
                    await session.execute(
                        text(
                            "SELECT slot_key,name,sequence FROM orbit_launch_name_item WHERE "
                            "tenant_id=:tenant AND reservation_id=:names "
                            "ORDER BY ordinal LIMIT 10001"
                        ),
                        params,
                    )
                )
                .mappings()
                .all()
            ]
            previous_success = (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM orbit_launch_validation WHERE tenant_id=:tenant
                        AND plan_id=:plan
                        """
                    ),
                    {"tenant": value.current.tenant_id, "plan": value.source.plan_id},
                )
            ).scalar_one()
        observations = (
            ObservationReference("ALLOCATION", allocation["id"], allocation["plan_revision"]),
            ObservationReference("NAME_RESERVATION", names["id"], names["plan_revision"]),
            ObservationReference("SCOPE", value.current.tenant_id, scope),
        )
        errors = (
            (
                ValidationIssue(
                    "/campaigns/0",
                    "CAPABILITY_UNVERIFIED",
                    "隔离协议显式业务invalid，不代表平台检查",
                ),
            )
            if "_INVALID_" in plan["name"] or ("_ONCE_" in plan["name"] and previous_success > 0)
            else ()
        )
        from task_core_fixture import compile_dag

        dag_count = compile_dag(plan).total_dag_node_count
        arguments = {
            "allocation": allocation,
            "name_reservation": names,
            "capability_version": "ISOLATED_PROTOCOL_NOT_PLATFORM",
            "policy_version": "ISOLATED_POLICY_NOT_PRODUCTION",
            "scope_version": scope,
            "channel_snapshot": {
                "fixture_plan_id": value.source.plan_id,
                "authority": "ISOLATED_TEST",
            },
            "product_snapshot": {
                "fixture_plan_id": value.source.plan_id,
                "authority": "ISOLATED_TEST",
            },
            "currency": "USD",
            "total_dag_node_count": dag_count,
        }
        fingerprint = digest(
            {
                "scope": scope,
                "plan_payload_hash": value.source.payload_hash,
                "allocation": allocation,
                "names": names,
            }
        )
        evidence = ValidationEvidence(
            fingerprint,
            scope,
            dag_count,
            errors,
            observations,
            None if errors else canonical(arguments).encode(),
        )
        if "_BARRIER_" in plan["name"]:
            directory = control_directory(database, self.control_dir)
            ready, release = (
                directory / (value.source.plan_id + ".ready"),
                directory / (value.source.plan_id + ".release"),
            )
            if ready.is_symlink() or release.is_symlink():
                raise ValueError("握手文件禁止符号链接")
            ready.write_text("ready", encoding="ascii")
            started = monotonic()
            try:
                while not release.exists():
                    if monotonic() - started >= 8:
                        raise OrbitError(
                            503, "LAUNCH_VALIDATION_AUTHORITY_UNAVAILABLE", "隔离握手超时"
                        )
                    await asyncio.sleep(0.025)
                if release.is_symlink() or release.read_text(encoding="ascii") != "release":
                    raise ValueError("隔离握手文件无效")
            finally:
                ready.unlink(missing_ok=True)
                release.unlink(missing_ok=True)
        return evidence

    async def revalidate(self, session, current, source, evidence):
        await guard(session)
        # 只取当前目录来源锁；allocation/name头与完整items由Store在launch/head后锁。
        actual_scope = await scope_version(session, current)
        if actual_scope != evidence.scope_version:
            raise OrbitError(409, "STALE_PREVIEW", "本轮真实目录水位变化")
        return evidence
