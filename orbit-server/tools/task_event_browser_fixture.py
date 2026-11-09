"""真实浏览器的隔离文件协同：只调用真实事务，不提供业务HTTP写入后门。"""

import asyncio
import json
import re
import threading
from collections import Counter
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

FIELDS = {"version", "run_id", "request_id", "action", "task_id", "node_id"}
ACTIONS = {"PUBLISH_RUNNING", "REVOKE_TASK_READ", "RESTORE_TASK_READ"}


def uuid_value(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("协同标识必须是规范UUID")
    return value


def validate_command(value, run_id):
    """拒绝额外字段、跨轮次、任意动作及客户端路径/SQL/身份参数。"""
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("协同请求字段无效")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("协同版本无效")
    if value["run_id"] != run_id or value["action"] not in ACTIONS:
        raise ValueError("协同轮次或动作无效")
    uuid_value(value["request_id"])
    uuid_value(value["task_id"])
    if value["action"] == "PUBLISH_RUNNING":
        uuid_value(value["node_id"])
    elif value["node_id"] is not None:
        raise ValueError("权限协同不能携带节点")
    return value


class TaskEventBrowserControl:
    """仅本轮13306/UUID库及990371专用角色，凭据始终只在进程内存。"""

    def __init__(self, admin, database, output):
        if (
            admin.host != "127.0.0.1"
            or admin.port != 13306
            or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        ):
            raise ValueError("浏览器协同仅允许独立UUID测试库")
        root = Path(__file__).resolve().parents[2]
        expected = (root / ".runtime/python-browser-it").resolve()
        if Path(output).resolve() != expected or not expected.is_relative_to(root.resolve()):
            raise ValueError("浏览器协同必须使用本工作区隔离证据目录")
        with admin.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            assert cursor.fetchone()[0] == database
            cursor.execute(
                "SELECT u.user_name,s.tenant_id,b.id,ur.role_id FROM sys_user u "
                "JOIN orbit_user_scope s ON s.user_id=u.user_id AND s.enabled=1 "
                "JOIN orbit_business_user b ON b.user_id=u.user_id AND b.tenant_id=s.tenant_id "
                "JOIN sys_user_role ur ON ur.user_id=u.user_id WHERE u.user_id=990371"
            )
            identities = cursor.fetchall()
            assert len(identities) == 1
            self.username, self.tenant, self.owner, self.role = identities[0]
            assert re.fullmatch(r"task_reader_[a-f0-9]{12}", self.username)
            cursor.execute("SELECT user_id FROM sys_user_role WHERE role_id=%s", (self.role,))
            assert {row[0] for row in cursor.fetchall()} == {990370, 990371, 990372}
            cursor.execute(
                "SELECT COUNT(*) FROM sys_role_menu WHERE role_id=%s AND menu_id=310206",
                (self.role,),
            )
            assert cursor.fetchone()[0] == 1
        admin.commit()

        def decoded(value):
            return value.decode() if isinstance(value, bytes) else value

        self.url = URL.create(
            "mysql+asyncmy",
            username=decoded(admin.user),
            password=decoded(admin.password),
            host=admin.host,
            port=admin.port,
            database=database,
        )
        self.run_id = str(uuid4())
        self.directory = expected / "task-event-control" / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.manifest = {"version": 1, "run_id": self.run_id, "directory": str(self.directory)}
        self.stopping, self.ready = threading.Event(), threading.Event()
        self.records, self.failures = [], []
        self.thread = threading.Thread(
            target=self._thread, name="orbit-task-event-fixture", daemon=True
        )
        self.closed = False

    def start(self):
        self.thread.start()
        if not self.ready.wait(3) or self.failures:
            self.stopping.set()
            self.thread.join(timeout=10)
            raise RuntimeError("浏览器协同未能就绪")
        return self

    def _thread(self):
        try:
            asyncio.run(self._run())
        except Exception:
            self.failures.append("CONTROL_WORKER_FAILED")
            self.ready.set()

    async def _run(self):
        from orbit_api.task_event_publisher import publish_fixture_running

        engine = create_async_engine(self.url, echo=False, connect_args={"connect_timeout": 3})
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        processed = {}

        async def operation(command):
            async with sessions() as session, session.begin():
                await session.execute(text("SET SESSION innodb_lock_wait_timeout=2"))
                params = {"tenant": self.tenant, "owner": self.owner, "task": command["task_id"]}
                task = (
                    await session.execute(
                        text(
                            "SELECT revision FROM orbit_task WHERE tenant_id=:tenant AND id=:task "
                            "AND owner_user_id=:owner AND manifest_phase='COMPLETE'"
                        ),
                        params,
                    )
                ).first()
                if task is None:
                    raise ValueError("协同对象不属于当前专用身份")
                if command["action"] == "PUBLISH_RUNNING":
                    event = await publish_fixture_running(
                        session,
                        1,
                        command["task_id"],
                        command["node_id"],
                        command["request_id"],
                        producer="ISOLATED_TEST",
                    )
                    current = (
                        await session.execute(
                            text(
                                "SELECT t.revision,n.state FROM orbit_task t "
                                "JOIN orbit_task_node n "
                                "ON n.tenant_id=t.tenant_id AND n.task_id=t.id WHERE "
                                "t.tenant_id=:tenant AND t.id=:task AND n.id=:node FOR SHARE"
                            ),
                            params | {"node": command["node_id"]},
                        )
                    ).first()
                    assert current and current[1] == "RUNNING" and current[0] > task[0]
                    revision = current[0]
                else:
                    event = None
                    if command["action"] == "REVOKE_TASK_READ":
                        changed = await session.execute(
                            text(
                                "DELETE FROM sys_role_menu WHERE role_id=:role AND menu_id=310206"
                            ),
                            {"role": self.role},
                        )
                        assert changed.rowcount == 1
                    else:
                        await session.execute(
                            text(
                                "INSERT IGNORE INTO sys_role_menu(role_id,menu_id) "
                                "VALUES(:role,310206)"
                            ),
                            {"role": self.role},
                        )
                    revision = task[0]
            # 仅在事务commit完成后发送APPLIED；页面仍必须核实际SSE与真实GET。
            self.records.append(command | {"task_revision": revision, "event_id": event})
            return revision

        async def restore():
            async with sessions() as session, session.begin():
                await session.execute(text("SET SESSION innodb_lock_wait_timeout=2"))
                await session.execute(
                    text("INSERT IGNORE INTO sys_role_menu(role_id,menu_id) VALUES(:role,310206)"),
                    {"role": self.role},
                )

        self.ready.set()
        try:
            while not self.stopping.is_set():
                for path in sorted(self.directory.glob("*.request.json")):
                    if path.name in processed:
                        if path.read_bytes() != processed[path.name]:
                            self.failures.append("CONTROL_REQUEST_CHANGED")
                            processed[path.name] = path.read_bytes()
                        continue
                    request_id = path.name.removesuffix(".request.json")
                    command = None
                    try:
                        uuid_value(request_id)
                        if path.stat().st_size > 2048:
                            raise ValueError("协同请求过大")
                        raw = path.read_bytes()
                        if len(raw) > 2048:
                            raise ValueError("协同请求过大")
                        command = validate_command(json.loads(raw.decode("utf-8")), self.run_id)
                        if command["request_id"] != request_id:
                            raise ValueError("协同文件与请求标识不一致")
                        revision = await asyncio.wait_for(operation(command), 4)
                        response = command | {
                            "state": "APPLIED",
                            "task_revision": revision,
                            "code": None,
                        }
                    except Exception:
                        self.failures.append("CONTROL_COMMAND_FAILED")
                        response = {
                            "version": 1,
                            "run_id": self.run_id,
                            "request_id": request_id,
                            "state": "FAILED",
                            "action": command["action"] if command else None,
                            "task_id": command["task_id"] if command else None,
                            "node_id": command["node_id"] if command else None,
                            "task_revision": None,
                            "code": "FIXTURE_CONTROL_FAILED",
                        }
                    temporary = self.directory / (request_id + ".response.tmp")
                    temporary.write_text(json.dumps(response), encoding="utf-8")
                    temporary.replace(self.directory / (request_id + ".response.json"))
                    processed[path.name] = raw if command else path.read_bytes()
                    if len(processed) > 32:
                        raise ValueError("浏览器协同次数超限")
                await asyncio.sleep(0.05)
        finally:
            try:
                await asyncio.wait_for(restore(), 4)
            finally:
                await engine.dispose()

    def stop(self):
        if self.closed:
            return
        self.stopping.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=10)
        if self.thread.is_alive():
            raise RuntimeError("浏览器协同仍未结束，不能标验收通过")
        self.closed = True

    def verify(self, admin, expected):
        self.stop()
        assert not self.failures, "浏览器协同存在失败，不能标验收通过"
        counts = Counter(record["action"] for record in self.records)
        assert counts == Counter(dict.fromkeys(ACTIONS, expected))
        # 用实际表再次对账，文件APPLIED不能代替持久事件/审计/outbox或权限恢复。
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM sys_role_menu WHERE role_id=%s AND menu_id=310206",
                (self.role,),
            )
            assert cursor.fetchone()[0] == 1
            for record in self.records:
                if record["action"] != "PUBLISH_RUNNING":
                    continue
                cursor.execute(
                    "SELECT e.task_revision,e.state,n.state FROM orbit_task_event e "
                    "JOIN orbit_task_node n ON n.tenant_id=e.tenant_id AND n.task_id=e.task_id "
                    "AND n.id=e.node_id JOIN orbit_task_audit a ON a.tenant_id=e.tenant_id "
                    "AND a.task_id=e.task_id AND a.request_id=e.request_id "
                    "JOIN orbit_task_outbox o ON o.audit_id=a.id WHERE "
                    "e.tenant_id=%s AND e.task_id=%s AND e.event_id=%s",
                    (self.tenant, record["task_id"], record["event_id"]),
                )
                assert list(cursor.fetchall()) == [(record["task_revision"], "RUNNING", "RUNNING")]
        admin.commit()
        return {
            "actual_commands": dict(counts),
            "process_or_platform_execution": False,
            "scope": "当前UUID库真实持久事件与fixture权限变更；不是平台执行",
        }
