"""Meta授权后的持久分页发现；逐项读取和账户创建仍由原账户导入Worker执行。"""

import hashlib
from dataclasses import asdict
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import text

from orbit_api.account_access import event
from orbit_api.account_contract import batch_summary, tokenize
from orbit_api.account_metadata import unknown_observation
from orbit_api.account_platform import AccountReadFailure
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_account_sources import invalidate_meta_read_source, load_connection
from orbit_api.meta_read_adapter import GraphReadTransport, MetaReadAdapter
from orbit_api.meta_read_contract import MetaReadFailure, ReadCheckpoint


async def authorizing_owner(session, actor, tenant):
    """仅采用发起授权的真实平台用户，不能采用代看主体或浏览器传入的投手。"""
    current = await require_business_access(
        session, actor, "accounts", "accounts.import", acting_subject=False
    )
    if current.tenant_id != tenant:
        raise OrbitError(403, "META_STATE_INVALID", "授权主体所属租户已变化")
    return current


async def enqueue(session, authorization, connection, revision, request_id):
    """调用方已锁账户时钟；与凭据发布、state消耗及审计使用同一事务。"""
    current = await authorizing_owner(
        session, authorization["actor_id"], authorization["tenant_id"]
    )
    if (
        current.subject_id != authorization["owner_user_id"]
        or current.team_id != authorization["owner_team_id"]
    ):
        raise OrbitError(403, "META_STATE_INVALID", "授权期间投放师或团队已变化，请重新授权")
    auth = (
        await session.execute(
            text("SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"),
            {"actor": current.actor_id},
        )
    ).scalar_one()
    scope = (
        await session.execute(
            text("SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR SHARE"),
            {"tenant": current.tenant_id},
        )
    ).scalar_one()
    params = dict(
        id=authorization["id"],
        tenant=current.tenant_id,
        actor=current.actor_id,
        subject=current.subject_id,
        team=current.team_id,
        connection=connection,
        version=revision,
        auth=auth,
        scope=scope,
        request=request_id,
    )
    await session.execute(
        text("""INSERT INTO orbit_meta_auto_import
        (tenant_id,id,connection_id,connection_revision,actor_id,owner_user_id,owner_team_id,
         actor_auth_version,scope_version,request_id,state,created_at,updated_at,next_attempt_at)
        VALUES(:tenant,:id,:connection,:version,:actor,:subject,:team,:auth,:scope,:request,
         'QUEUED',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"""),
        params,
    )
    await event(
        session,
        current,
        "META_AUTO_IMPORT",
        authorization["id"],
        1,
        "META_AUTO_IMPORT_QUEUED",
        request_id,
        {"connection_id": connection},
    )


def public_status(task, batches):
    """只汇总既有批次真实计数，发现未完成不能冒充全部账户导入成功。"""
    result = {key: task[key] for key in ("id", "state", "error_code")}
    result["batches"] = batches
    for key in ("total", "success_count", "failed_count", "duplicate_count"):
        result[key] = sum(batch[key] for batch in batches)
    if result["state"] == "IMPORTING":
        if any(batch["state"] in {"QUEUED", "RUNNING"} for batch in batches):
            return result
        result["state"] = (
            ("PARTIAL_SUCCESS" if result["success_count"] else "FAILED")
            if result["failed_count"]
            else "SUCCEEDED"
        )
    return result


async def latest_status(session, tenant, connection):
    task = (
        (
            await session.execute(
                text(
                    "SELECT id,state,error_code FROM orbit_meta_auto_import WHERE "
                    "tenant_id=:tenant AND connection_id=:connection ORDER BY created_at "
                    "DESC,id DESC LIMIT 1"
                ),
                dict(tenant=tenant, connection=connection),
            )
        )
        .mappings()
        .first()
    )
    if task is None:
        return None
    batches = (
        (
            await session.execute(
                text("""SELECT b.id,b.state,b.total,b.success_count,b.failed_count,b.duplicate_count
        FROM orbit_meta_auto_import_batch x JOIN orbit_account_import b
        ON b.tenant_id=x.tenant_id AND b.id=x.batch_id
        WHERE x.tenant_id=:tenant AND x.task_id=:task ORDER BY x.page_number"""),
                dict(tenant=tenant, task=task["id"]),
            )
        )
        .mappings()
        .all()
    )
    return public_status(task, [dict(row) for row in batches])


class MetaAutoImportWorker:
    """单页短租约；检查点与原批次原子提交，崩溃后重取未提交页且拒绝迟到发布。"""

    def __init__(self, sessions, cipher, graph_version, *, adapter_factory=None):
        self.sessions, self.cipher, self.graph_version = sessions, cipher, graph_version
        self.adapter_factory = adapter_factory

    @staticmethod
    def audit_context(task):
        return SimpleNamespace(
            tenant_id=task["tenant_id"], actor_id=task["actor_id"], subject_id=task["owner_user_id"]
        )

    async def locked(self, session, task):
        from orbit_api.meta_connection_service import lock_account_clock

        await lock_account_clock(session, task["tenant_id"])
        return (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_meta_auto_import WHERE tenant_id=:tenant AND "
                        "id=:id FOR UPDATE"
                    ),
                    dict(tenant=task["tenant_id"], id=task["id"]),
                )
            )
            .mappings()
            .first()
        )

    @staticmethod
    def owns_lease(latest, claimed):
        return (
            latest is not None
            and latest["state"] == "DISCOVERING"
            and latest["claim_id"] == claimed["claim_id"]
        )

    async def verify(self, session, task):
        current = await authorizing_owner(session, task["actor_id"], task["tenant_id"])
        if current.subject_id != task["owner_user_id"] or current.team_id != task["owner_team_id"]:
            raise AccountReadFailure("ACCOUNT_IMPORT_AUTHORIZATION_CHANGED")
        auth = (
            await session.execute(
                text(
                    "SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"
                ),
                {"actor": current.actor_id},
            )
        ).scalar_one()
        scope = (
            await session.execute(
                text(
                    "SELECT revision FROM orbit_directory_clock WHERE tenant_id=:tenant FOR SHARE"
                ),
                {"tenant": current.tenant_id},
            )
        ).scalar_one()
        if auth != task["actor_auth_version"] or scope != task["scope_version"]:
            raise AccountReadFailure("ACCOUNT_IMPORT_AUTHORIZATION_CHANGED")
        source = await load_connection(
            session,
            self.cipher,
            task["tenant_id"],
            task["connection_id"],
            task["connection_revision"],
            self.graph_version,
        )
        if source.kind != "LOGIN":
            raise AccountReadFailure("META_CONNECTION_SOURCE_CHANGED")
        return source

    async def claim(self):
        async with self.sessions() as session, session.begin():
            candidate = (
                (
                    await session.execute(
                        text("""SELECT tenant_id,id FROM orbit_meta_auto_import
                WHERE (state='QUEUED' AND next_attempt_at<=UTC_TIMESTAMP(3)) OR
                (state='DISCOVERING' AND claimed_at<UTC_TIMESTAMP(3)-INTERVAL 120 SECOND)
                ORDER BY updated_at,id LIMIT 1""")
                    )
                )
                .mappings()
                .first()
            )
            if candidate is None:
                return None
            task = await self.locked(session, candidate)
            # 候选查询不持锁，必须在账户时钟之后重新检查租约是否仍可领取。
            eligible = (
                await session.execute(
                    text("""SELECT id FROM orbit_meta_auto_import WHERE tenant_id=:tenant AND id=:id
                AND ((state='QUEUED' AND next_attempt_at<=UTC_TIMESTAMP(3)) OR
                (state='DISCOVERING' AND claimed_at<UTC_TIMESTAMP(3)-INTERVAL 120 SECOND))"""),
                    dict(tenant=candidate["tenant_id"], id=candidate["id"]),
                )
            ).scalar_one_or_none()
            if eligible is None:
                return None
            if task["attempts"] >= 4:
                await self.finish_error(session, task, "ACCOUNT_READ_INTERRUPTED", False)
                return None
            claim = str(uuid4())
            await session.execute(
                text("""UPDATE orbit_meta_auto_import SET state='DISCOVERING',claim_id=:claim,
                claimed_at=UTC_TIMESTAMP(3),attempts=attempts+1,revision=revision+1,
                updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:id"""),
                dict(tenant=task["tenant_id"], id=task["id"], claim=claim),
            )
            await event(
                session,
                self.audit_context(task),
                "META_AUTO_IMPORT",
                task["id"],
                task["revision"] + 1,
                "META_AUTO_IMPORT_CLAIMED",
                task["request_id"],
                {},
            )
            return dict(task) | dict(
                state="DISCOVERING",
                claim_id=claim,
                attempts=task["attempts"] + 1,
                revision=task["revision"] + 1,
            )

    async def preflight(self, task):
        async with self.sessions() as session, session.begin():
            latest = await self.locked(session, task)
            if not self.owns_lease(latest, task):
                raise AccountReadFailure("ACCOUNT_IMPORT_CLAIM_EXPIRED")
            return await self.verify(session, latest)

    async def publish(self, task, page):
        async with self.sessions() as session, session.begin():
            latest = await self.locked(session, task)
            if not self.owns_lease(latest, task):
                return False
            await self.verify(session, latest)
            if not page.complete and page.checkpoint is None:
                raise AccountReadFailure("ACCOUNT_PLATFORM_SCOPE_INCOMPLETE")
            # 检查点与新增原导入批次只在此事务发布，重启不会遗漏或重复已提交页。
            page_number = latest["page_number"] + 1
            if page.items:
                await self.create_batch(session, latest, page.items, page_number)
            state = "IMPORTING" if page.complete else "QUEUED"
            await session.execute(
                text("""UPDATE orbit_meta_auto_import SET state=:state,
                checkpoint_json=:checkpoint,page_number=:page,attempts=0,claim_id=NULL,claimed_at=NULL,
                error_code=NULL,revision=revision+1,next_attempt_at=UTC_TIMESTAMP(3),updated_at=UTC_TIMESTAMP(3)
                WHERE tenant_id=:tenant AND id=:id"""),
                dict(
                    tenant=task["tenant_id"],
                    id=task["id"],
                    state=state,
                    page=page_number,
                    checkpoint=canonical(asdict(page.checkpoint)) if page.checkpoint else None,
                ),
            )
            await event(
                session,
                self.audit_context(latest),
                "META_AUTO_IMPORT",
                task["id"],
                latest["revision"] + 1,
                "META_AUTO_IMPORT_PAGE",
                task["request_id"],
                {"page": page_number, "count": len(page.items), "complete": page.complete},
            )
            return True

    async def create_batch(self, session, task, items, page_number):
        identifier = str(uuid4())
        raw = "\n".join(item["account_id"] for item in items)
        rows = tokenize(raw)
        summary = batch_summary([row["state"] for row in rows], started=False)
        params = (
            dict(
                tenant=task["tenant_id"],
                id=identifier,
                task=task["id"],
                page=page_number,
                actor=task["actor_id"],
                subject=task["owner_user_id"],
                team=task["owner_team_id"],
                scope=task["scope_version"],
                auth=task["actor_auth_version"],
                request=task["request_id"],
                hash=hashlib.sha256(raw.encode()).hexdigest(),
                raw=raw,
                connection=task["connection_id"],
                version=task["connection_revision"],
            )
            | summary
        )
        await session.execute(
            text("""INSERT INTO orbit_account_import
            (tenant_id,id,vendor_id,vendor_revision,owner_user_id,owner_team_id,actor_id,actor_subject_id,
             scope_version,input_hash,input_ref,state,total,success_count,failed_count,duplicate_count,
             actor_auth_version,source_config_id,source_config_revision,request_id,created_at,updated_at)
            VALUES(:tenant,:id,NULL,NULL,:subject,:team,:actor,:subject,:scope,:hash,NULL,
             :state,:total,:success_count,:failed_count,:duplicate_count,:auth,:connection,:version,:request,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"""),
            params,
        )
        await session.execute(
            text("""INSERT INTO orbit_meta_auto_import_batch
            (tenant_id,task_id,batch_id,page_number,input_text)
            VALUES(:tenant,:task,:id,:page,:raw)"""),
            params,
        )
        await session.execute(
            text("""INSERT INTO orbit_meta_import_source
            (tenant_id,batch_id,connection_id,connection_revision,channel_id,discovery_task_id)
            VALUES(:tenant,:id,:connection,:version,NULL,:task)"""),
            params,
        )
        public = [
            dict(
                id=str(uuid4()),
                **row,
                account_id=None,
                name=None,
                spend=unknown_observation("XXX"),
                retryable=False,
                error_code="IMPORT_ID_INVALID" if row["state"] == "INVALID" else None,
                observed_at=None,
            )
            for row in rows
        ]
        await session.execute(
            text("""INSERT INTO orbit_account_import_row
            (tenant_id,id,batch_id,token_index,line_no,column_no,raw_display,normalized_id,duplicate_of,state,next_attempt_at,value_json)
            VALUES(:tenant,:id,:batch,:token_index,:line_no,:column,:raw_display,:normalized_id,:duplicate_of,:state,UTC_TIMESTAMP(3),:result)"""),
            [
                dict(tenant=task["tenant_id"], batch=identifier, result=canonical(row), **row)
                for row in public
            ],
        )
        await event(
            session,
            self.audit_context(task),
            "IMPORT",
            identifier,
            1,
            "IMPORT_ACCEPTED",
            task["request_id"],
            {"input_hash": params["hash"], "total": len(rows), "discovery_task_id": task["id"]},
        )

    async def finish_error(self, session, task, code, retryable):
        retry = retryable and task["attempts"] < 4
        await session.execute(
            text("""UPDATE orbit_meta_auto_import SET state=:state,error_code=:code,
            claim_id=NULL,claimed_at=NULL,revision=revision+1,updated_at=UTC_TIMESTAMP(3),
            next_attempt_at=UTC_TIMESTAMP(3)+INTERVAL 60 SECOND
            WHERE tenant_id=:tenant AND id=:id"""),
            dict(
                tenant=task["tenant_id"],
                id=task["id"],
                state="QUEUED" if retry else "FAILED",
                code=code,
            ),
        )
        await event(
            session,
            self.audit_context(task),
            "META_AUTO_IMPORT",
            task["id"],
            task["revision"] + 1,
            "META_AUTO_IMPORT_FAILED",
            task["request_id"],
            {"error_code": code, "retryable": retry},
        )

    async def fail(self, task, error):
        async with self.sessions() as session, session.begin():
            latest = await self.locked(session, task)
            if not self.owns_lease(latest, task):
                return
            # 平台明确190失效才能撤销连接；不记录外部异常正文或凭据。
            if error.code == "META_AUTH_FAILED":
                try:
                    source = await self.verify(session, latest)
                except (OrbitError, AccountReadFailure):
                    source = None
                if source is not None:
                    await invalidate_meta_read_source(
                        session,
                        self.audit_context(latest),
                        source,
                        error.code,
                        latest["request_id"],
                    )
            await self.finish_error(session, latest, error.code, getattr(error, "retryable", False))

    async def run_once(self, limit=10):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("单轮分页上限必须为1至100")
        processed = 0
        for _ in range(limit):
            task = await self.claim()
            if task is None:
                break
            processed += 1
            guard_failure = None
            try:
                source = await self.preflight(task)
                if self.adapter_factory:
                    adapter = self.adapter_factory(source.configuration)
                else:
                    worker = self

                    class GuardedTransport:
                        async def request(self, *args, _worker=worker, _task=task, **kwargs):
                            nonlocal guard_failure
                            try:
                                await _worker.preflight(_task)
                            except (AccountReadFailure, OrbitError) as error:
                                guard_failure = error
                                raise MetaReadFailure("META_READ_FORBIDDEN") from None
                            return await GraphReadTransport().request(*args, **kwargs)

                    adapter = MetaReadAdapter(source.configuration, transport=GuardedTransport())
                checkpoint = (
                    ReadCheckpoint(**_decode(task["checkpoint_json"]))
                    if task["checkpoint_json"]
                    else None
                )
                page = await adapter.accounts_page(checkpoint=checkpoint)
                await self.publish(task, page)
            except (AccountReadFailure, MetaReadFailure, OrbitError) as error:
                await self.fail(task, guard_failure or error)
        return processed
