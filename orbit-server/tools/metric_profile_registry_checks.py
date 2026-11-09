"""040真实MySQL指标来源协议；只有UUID隔离SQL夹具，不证明Meta核验或平台写授权。"""

import asyncio
import json
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

METRIC_PROFILE_REGISTRY_CASES = [
    "pythonMetricRegistryActualCaptureOutsideTransactionAndAtomicPublication",
    "pythonMetricRegistryExactReplayPreservesVersionAuditOutboxClock",
    "pythonMetricRegistryReleasePermissionCannotBeReplacedByLaunchActions",
    "pythonMetricRegistryCreateEditExecuteUseExactCallerActionWithoutOwnerRead",
    "pythonMetricRegistryCurrentOwnerIdentityScopeAndTenantAreRechecked",
    "pythonMetricRegistryExactVersionAdapterAndExplicitMappingAreRequired",
    "pythonMetricRegistryChangedCaptureSourceRejectedBeforeAnyPublication",
    "pythonMetricRegistryImmutablePayloadMappingAndSourceCannotBeRebound",
    "pythonMetricRegistryActualHashChecksAndCompositeForeignKeysRejectInvalidRows",
    "pythonMetricRegistryActualVersionAdapterAuditTriggersAreImmutable",
    "pythonMetricRegistryActualAudit1644RollsBackAllSixRegistryTables",
    "pythonMetricRegistryPreciseBindingAndWholeProfileRevocationCannotResurrect",
    "pythonMetricRegistryOrphanVersionInvisibleAndExactIndexExplain",
]


def validate_metric_registry_target(admin, database):
    if (
        not isinstance(database, str)
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("040专项仅允许固定127.0.0.1:13306 UUID隔离数据库")


def metric_registry_publication_fixture(suffix):
    """构造原DTO真实可解析的隔离来源，显式声明没有META配置来源。"""
    from orbit_api.metric_profile_contract import MetricSourceProof, publication

    profile = {
        "id": str(uuid4()),
        "version": "observed-string-release",
        "source": "FIXTURE",
        "register_action_type": None,
        "purchase_action_type": "observed-purchase",
        "value_action_type": None,
        "attribution_windows": ["opaque-original-window"],
        "action_report_time": "explicit-report-time",
        "timezone_policy": "ACCOUNT_LOCAL",
        "breakdown": "TOTAL",
        "maturity_days": 28,
        "verified": True,
    }
    proof = MetricSourceProof(
        "a" * 64, datetime.now(UTC) - timedelta(seconds=1), "isolated-sql:" + suffix, None, None
    )
    prepared = publication(
        profile,
        "explicit-adapter-A",
        [{"event_type": "EXPLICIT_EVENT", "window_days": 7}],
        proof,
    )
    return profile, prepared


def run_metric_profile_registry_checks(admin, database, cases):
    validate_metric_registry_target(admin, database)
    from orbit_api.authorization import (
        BusinessContext,
        require_business_access,
        require_system_access,
    )
    from orbit_api.errors import OrbitError
    from orbit_api.metric_profile_contract import publication
    from orbit_api.metric_profile_store import MetricProfileAuthority, MetricProfileStore

    suffix = uuid4().hex[:16]
    source_table, trigger = "it_metric_source_" + suffix, "it_metric_audit_" + suffix
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, _, team = cursor.fetchone()
        cursor.execute(
            "CREATE TABLE " + source_table + "(id CHAR(36) PRIMARY KEY,sha CHAR(64) NOT NULL)"
        )
        cursor.execute(
            "INSERT IGNORE INTO orbit_metric_profile_clock(tenant_id) VALUES(%s)", (tenant,)
        )
        cursor.execute("SELECT COALESCE(MAX(user_id),0)+1 FROM sys_user")
        actor, owner = int(cursor.fetchone()[0]), None
        owner = actor + 1
        cursor.execute("SELECT COALESCE(MAX(role_id),0)+1 FROM sys_role")
        role = int(cursor.fetchone()[0])
        cursor.execute(
            "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,data_scope,status,del_flag) "
            "VALUES(%s,%s,%s,1,'1','0','0')",
            (role, "指标来源动作fixture", "metric_" + suffix),
        )
        for menu in (31000, 31020, 31022, 31023, 31024):
            cursor.execute("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", (role, menu))
        contexts = []
        for native in (actor, owner):
            identifier = str(uuid4())
            cursor.execute(
                "INSERT INTO sys_user(user_id,user_name,nick_name,password,status,del_flag) "
                "SELECT %s,%s,'指标隔离身份',password,'0','0' FROM sys_user WHERE user_id=1",
                (native, "metric_" + suffix + "_" + str(native)),
            )
            cursor.execute(
                "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
                "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                (native, str(uuid4())),
            )
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
                (native, tenant),
            )
            cursor.execute(
                "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,"
                "display_name,invited,created_at) "
                "VALUES(%s,%s,%s,%s,'指标隔离身份',0,UTC_TIMESTAMP(3))",
                (tenant, identifier, native, team),
            )
            contexts.append(BusinessContext(native, tenant, "USER", identifier, team))
        cursor.execute("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (actor, role))
    admin.commit()
    caller, target = contexts

    def sql(statement, values=(), *, rows=False):
        with admin.cursor() as cursor:
            cursor.execute(statement, values)
            result = cursor.fetchall() if rows else None
        admin.commit()
        return result

    def snapshot():
        counts = tuple(
            sql("SELECT COUNT(*) FROM orbit_metric_profile_" + table, rows=True)[0][0]
            for table in ("version", "head", "adapter", "audit", "outbox")
        )
        return counts + (
            sql(
                "SELECT revision FROM orbit_metric_profile_clock WHERE tenant_id=%s",
                (tenant,),
                rows=True,
            )[0][0],
        )

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    class SqlFixtureAuthority(MetricProfileAuthority):
        kind = "ISOLATED_TEST"

        def __init__(self, value):
            self.value = value
            self.captures = 0
            self.revalidations = 0

        async def capture(self, profile_id, version, adapter_version):
            # 没有SQL session参数；真正publish事务尚未打开。
            assert sql(
                "SELECT sha FROM " + source_table + " WHERE id=%s", (profile_id,), rows=True
            ) == ((self.value.proof.source_sha256,),)
            self.captures += 1
            return self.value

        async def revalidate(self, session, current, prepared):
            assert session.in_transaction()
            actual = (
                await session.execute(
                    text("SELECT sha FROM " + source_table + " WHERE id=:id FOR SHARE"),
                    {"id": prepared.profile()["id"]},
                )
            ).scalar_one()
            self.revalidations += 1
            if actual != prepared.proof.source_sha256:
                raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "隔离来源已改版")
            return prepared.proof

    def fixture():
        profile, prepared = metric_registry_publication_fixture(suffix)
        sql(
            "INSERT INTO " + source_table + "(id,sha) VALUES(%s,%s)",
            (profile["id"], prepared.proof.source_sha256),
        )
        authority = SqlFixtureAuthority(prepared)
        return profile, prepared, authority, MetricProfileStore(authority)

    async def run():
        engine = create_async_engine(
            URL.create(
                "mysql+asyncmy",
                username=decoded(admin.user),
                password=decoded(admin.password),
                host=admin.host,
                port=admin.port,
                database=database,
            ),
            echo=False,
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def call(method, *args, **kwargs):
            async with sessions() as session, session.begin():
                return await method(session, *args, **kwargs)

        async def rejected(method, *args, status, code=None, **kwargs):
            try:
                await call(method, *args, **kwargs)
            except OrbitError as error:
                assert error.status == status and (code is None or error.code == code), {
                    "status": error.status,
                    "code": error.code,
                }
            else:
                raise AssertionError("指标来源必须明确拒绝，不可默许成功")

        def invalid(statement, values, errors):
            try:
                with admin.cursor() as cursor:
                    cursor.execute(statement, values)
            except Exception as error:
                admin.rollback()
                assert error.args[0] in errors, {"errno": error.args[0]}
            else:
                admin.rollback()
                raise AssertionError("040存储约束未拒绝非法行")

        try:
            current = await call(require_system_access, 1, 31086, "system.release.manage")
            profile, prepared, authority, store = fixture()
            captured = await store.prepare(
                profile["id"], profile["version"], prepared.adapter_version
            )
            assert captured == prepared and authority.captures == 1 and authority.revalidations == 0
            before = snapshot()
            head = await call(store.publish, current, captured, 0, str(uuid4()))
            after = snapshot()
            assert head["revision"] == 1 and after == tuple(value + 1 for value in before)
            assert authority.revalidations == 1
            cases.append(METRIC_PROFILE_REGISTRY_CASES[0])

            assert await call(store.publish, current, captured, 0, str(uuid4())) == head
            assert snapshot() == after and authority.revalidations == 2
            cases.append(METRIC_PROFILE_REGISTRY_CASES[1])

            await rejected(
                store.publish,
                caller,
                prepared,
                1,
                str(uuid4()),
                status=403,
                code="PERMISSION_DENIED",
            )
            assert snapshot() == after
            cases.append(METRIC_PROFILE_REGISTRY_CASES[2])

            for action in ("launch.create", "launch.edit", "launch.execute"):
                assert await call(require_business_access, actor, "launch", action) == caller
                result = await call(
                    store.lock_exact,
                    caller,
                    target,
                    profile["id"],
                    profile["version"],
                    prepared.adapter_version,
                    permission=action,
                )
                assert result["profile"] == profile and result["attribution_spec"] == [
                    {"event_type": "EXPLICIT_EVENT", "window_days": 7}
                ]
                leaf = {"launch.create": 31022, "launch.edit": 31023, "launch.execute": 31024}[
                    action
                ]
                sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s", (role, leaf))
                try:
                    await rejected(
                        store.lock_exact,
                        caller,
                        target,
                        profile["id"],
                        profile["version"],
                        prepared.adapter_version,
                        permission=action,
                        status=403,
                        code="PERMISSION_DENIED",
                    )
                finally:
                    sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", (role, leaf))
            await rejected(require_business_access, owner, "launch", "launch.read", status=403)
            await rejected(require_business_access, actor, "launch", "launch.read", status=403)
            cases.append(METRIC_PROFILE_REGISTRY_CASES[3])

            for column, value in (("enabled", 0), ("invited", 1)):
                sql(
                    "UPDATE orbit_business_user SET " + column + "=%s WHERE user_id=%s",
                    (value, owner),
                )
                try:
                    await rejected(
                        store.lock_exact,
                        caller,
                        target,
                        profile["id"],
                        profile["version"],
                        prepared.adapter_version,
                        status=404,
                    )
                finally:
                    sql(
                        "UPDATE orbit_business_user SET " + column + "=%s WHERE user_id=%s",
                        (1 - value, owner),
                    )
            for changed in (
                replace(target, subject_id=str(uuid4())),
                replace(target, team_id=str(uuid4())),
                replace(target, data_role="TEAM_ADMIN"),
                replace(target, tenant_id=str(uuid4())),
            ):
                await rejected(
                    store.lock_exact,
                    caller,
                    changed,
                    profile["id"],
                    profile["version"],
                    prepared.adapter_version,
                    status=404,
                )
            cases.append(METRIC_PROFILE_REGISTRY_CASES[4])

            for version, adapter in (
                ("UNKNOWN", prepared.adapter_version),
                (profile["version"], "UNKNOWN"),
            ):
                await rejected(
                    store.lock_exact, caller, target, profile["id"], version, adapter, status=404
                )
            locked = await call(
                store.lock_exact,
                caller,
                target,
                profile["id"],
                profile["version"],
                prepared.adapter_version,
            )
            assert (
                locked["bound_profile_version"] == profile["version"]
                and locked["profile_source_hash"] == prepared.profile_hash
            )
            assert locked["profile"]["attribution_windows"] == ["opaque-original-window"]
            # 结构合法但规范摘要/来源证明不相符的直接SQL夹具，不可被精确读默许。
            for bad_adapter, mapping_hash, proof_json in (
                ("isolated-corrupt-mapping", "b" * 64, None),
                ("isolated-corrupt-proof", prepared.attribution_hash, '{"changed":true}'),
            ):
                sql(
                    "INSERT INTO orbit_metric_profile_adapter(tenant_id,profile_id,profile_version,"
                    "adapter_version,registry_revision,profile_hash,mapping_json,mapping_hash,"
                    "source_proof_json) SELECT tenant_id,profile_id,profile_version,%s,"
                    "registry_revision,profile_hash,mapping_json,%s,"
                    + ("source_proof_json" if proof_json is None else "%s")
                    + " FROM orbit_metric_profile_adapter WHERE tenant_id=%s AND profile_id=%s "
                    "AND adapter_version=%s",
                    (bad_adapter, mapping_hash)
                    + (() if proof_json is None else (proof_json,))
                    + (tenant, profile["id"], prepared.adapter_version),
                )
                await rejected(
                    store.lock_exact,
                    caller,
                    target,
                    profile["id"],
                    profile["version"],
                    bad_adapter,
                    status=503,
                    code="METRIC_PROFILE_AUTHORITY_UNAVAILABLE",
                )
            cases.append(METRIC_PROFILE_REGISTRY_CASES[5])

            p2, v2, a2, s2 = fixture()
            v2 = await s2.prepare(p2["id"], p2["version"], v2.adapter_version)
            sql("UPDATE " + source_table + " SET sha=%s WHERE id=%s", ("b" * 64, p2["id"]))
            before_source = snapshot()
            await rejected(
                s2.publish,
                current,
                v2,
                0,
                str(uuid4()),
                status=409,
                code="METRIC_PROFILE_SOURCE_CHANGED",
            )
            assert snapshot() == before_source and a2.revalidations == 1
            cases.append(METRIC_PROFILE_REGISTRY_CASES[6])

            for replacement in (
                publication(
                    profile | {"maturity_days": 29},
                    prepared.adapter_version,
                    json.loads(prepared.attribution_json),
                    prepared.proof,
                ),
                publication(
                    profile,
                    prepared.adapter_version,
                    [{"event_type": "DIFFERENT", "window_days": 1}],
                    prepared.proof,
                ),
            ):
                await rejected(
                    store.publish,
                    current,
                    replacement,
                    1,
                    str(uuid4()),
                    status=409,
                    code="METRIC_PROFILE_IMMUTABLE_CONFLICT",
                )
            assert snapshot() == before_source
            cases.append(METRIC_PROFILE_REGISTRY_CASES[7])

            # INSERT SELECT触发实际CHECK/FK；永不修改已发布版本或关闭约束。
            version_columns = (
                "tenant_id,profile_id,version,payload_json,payload_hash,source,authority_kind,"
                "observed_at,evidence_ref,source_sha256,source_proof_json,created_by"
            )
            for field, value in (
                ("payload_hash", "A" * 64),
                ("payload_hash", "a" * 63),
                ("source_sha256", "g" * 64),
                ("source_sha256", "a" * 63),
            ):
                expressions = [
                    "%s" if name in {"profile_id", field} else name
                    for name in version_columns.split(",")
                ]
                invalid(
                    "INSERT INTO orbit_metric_profile_version("
                    + version_columns
                    + ") SELECT "
                    + ",".join(expressions)
                    + " FROM orbit_metric_profile_version WHERE tenant_id=%s AND profile_id=%s",
                    (str(uuid4()), value, tenant, profile["id"]),
                    {3819},
                )
            adapter_columns = (
                "tenant_id,profile_id,profile_version,adapter_version,registry_revision,"
                "profile_hash,mapping_json,mapping_hash,source_proof_json"
            )
            for field in ("profile_hash", "mapping_hash"):
                expressions = [
                    "%s" if name in {"adapter_version", field} else name
                    for name in adapter_columns.split(",")
                ]
                invalid(
                    "INSERT INTO orbit_metric_profile_adapter("
                    + adapter_columns
                    + ") SELECT "
                    + ",".join(expressions)
                    + " FROM orbit_metric_profile_adapter WHERE tenant_id=%s AND profile_id=%s",
                    (uuid4().hex, "X" * 64, tenant, profile["id"]),
                    {3819, 1452},
                )
            invalid(
                "INSERT INTO orbit_metric_profile_head(tenant_id,id,current_version,"
                "revision,state) "
                "VALUES(%s,%s,'missing',1,'ENABLED')",
                (tenant, str(uuid4())),
                {1452},
            )
            invalid(
                "INSERT INTO orbit_metric_profile_outbox(tenant_id,event_id) VALUES(%s,%s)",
                (tenant, str(uuid4())),
                {1452},
            )
            cases.append(METRIC_PROFILE_REGISTRY_CASES[8])

            for statement in (
                "UPDATE orbit_metric_profile_version SET payload_hash=payload_hash "
                "WHERE tenant_id=%s AND profile_id=%s",
                "DELETE FROM orbit_metric_profile_version WHERE tenant_id=%s AND profile_id=%s",
                "UPDATE orbit_metric_profile_adapter SET mapping_hash='"
                + "b" * 64
                + "' WHERE tenant_id=%s AND profile_id=%s",
                "DELETE FROM orbit_metric_profile_adapter WHERE tenant_id=%s AND profile_id=%s",
                "UPDATE orbit_metric_profile_audit SET action=action "
                "WHERE tenant_id=%s AND profile_id=%s",
                "DELETE FROM orbit_metric_profile_audit WHERE tenant_id=%s AND profile_id=%s",
            ):
                invalid(statement, (tenant, profile["id"]), {1644})
            cases.append(METRIC_PROFILE_REGISTRY_CASES[9])

            p3, v3, _, s3 = fixture()
            before_rollback = snapshot()
            sql(
                "CREATE TRIGGER "
                + trigger
                + " BEFORE INSERT ON orbit_metric_profile_audit FOR EACH ROW "
                "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='ISOLATED_METRIC_AUDIT_REJECT'"
            )
            try:
                try:
                    await call(s3.publish, current, v3, 0, str(uuid4()))
                except DBAPIError as error:
                    assert error.orig.args[0] == 1644
                else:
                    raise AssertionError("审计失败不得部分提交")
                assert snapshot() == before_rollback
            finally:
                sql("DROP TRIGGER IF EXISTS " + trigger)
            assert (await call(s3.publish, current, v3, 0, str(uuid4())))["revision"] == 1
            cases.append(METRIC_PROFILE_REGISTRY_CASES[10])

            second_adapter = publication(
                profile, "explicit-adapter-B", json.loads(prepared.attribution_json), prepared.proof
            )
            assert (await call(store.publish, current, second_adapter, 1, str(uuid4())))[
                "revision"
            ] == 2
            await call(
                store.revoke_binding,
                current,
                profile["id"],
                profile["version"],
                prepared.adapter_version,
                2,
                str(uuid4()),
            )
            await rejected(
                store.lock_exact,
                caller,
                target,
                profile["id"],
                profile["version"],
                prepared.adapter_version,
                status=404,
            )
            await call(
                store.lock_exact,
                caller,
                target,
                profile["id"],
                profile["version"],
                second_adapter.adapter_version,
            )
            await rejected(
                store.publish,
                current,
                prepared,
                3,
                str(uuid4()),
                status=409,
                code="METRIC_PROFILE_REVOKED",
            )
            await call(store.revoke, current, profile["id"], 3, str(uuid4()))
            await rejected(
                store.lock_exact,
                caller,
                target,
                profile["id"],
                profile["version"],
                second_adapter.adapter_version,
                status=404,
            )
            await rejected(
                store.publish,
                current,
                second_adapter,
                4,
                str(uuid4()),
                status=409,
                code="METRIC_PROFILE_REVOKED",
            )
            cases.append(METRIC_PROFILE_REGISTRY_CASES[11])

            orphan = str(uuid4())
            sql(
                "INSERT INTO orbit_metric_profile_version("
                + version_columns
                + ") SELECT tenant_id,%s,version,payload_json,payload_hash,source,authority_kind,"
                "observed_at,evidence_ref,source_sha256,source_proof_json,created_by "
                "FROM orbit_metric_profile_version WHERE tenant_id=%s AND profile_id=%s",
                (orphan, tenant, profile["id"]),
            )
            await rejected(
                store.lock_exact,
                caller,
                target,
                orphan,
                profile["version"],
                second_adapter.adapter_version,
                status=404,
            )
            with admin.cursor() as cursor:
                cursor.execute(
                    "EXPLAIN SELECT * FROM orbit_metric_profile_adapter "
                    "WHERE tenant_id=%s AND profile_id=%s "
                    "AND profile_version=%s AND adapter_version=%s",
                    (tenant, profile["id"], profile["version"], second_adapter.adapter_version),
                )
                columns = [column[0] for column in cursor.description]
                explanation = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
            admin.commit()
            assert len(explanation) == 1 and explanation[0]["key"] == "PRIMARY"
            cases.append(METRIC_PROFILE_REGISTRY_CASES[12])
            return {
                "registry_cases": len(METRIC_PROFILE_REGISTRY_CASES),
                "authority": "ISOLATED_SQL_NOT_META",
                "exact_lookup_index": "PRIMARY",
            }
        finally:
            await engine.dispose()

    try:
        return asyncio.run(run())
    finally:
        admin.rollback()
        sql("DROP TRIGGER IF EXISTS " + trigger)
        sql("DROP TABLE IF EXISTS " + source_table)
