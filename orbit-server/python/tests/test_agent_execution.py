"""真实SQLite执行日志与隔离设备/页面边界；不连接广告平台。"""

import importlib
import importlib.util
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest


def api():
    assert importlib.util.find_spec("orbit_agent.execution") is not None, "执行消费者缺失"
    return importlib.import_module("orbit_agent.execution")


def fixture_values():
    lease = {
        k: str(uuid4())
        for k in ("id", "operation_id", "task_id", "node_id", "attempt_id", "profile_binding_id")
    }
    lease.update(
        expires_at=(datetime.now(UTC) + timedelta(seconds=120)).isoformat(),
        fencing_token=1,
        workflow_version="pause_entity_v1",
        adapter_version="isolated_v1",
    )
    instruction = dict(
        lease_id=lease["id"],
        account_id=str(uuid4()),
        external_account_id="123",
        node_key="pause:1",
        kind="PAUSE",
        target=None,
        plan=None,
        manual=None,
        policy_version="v1",
        submission_group_id=None,
        allowed_until=lease["expires_at"],
        execution_manifest_id=None,
        execution_manifest_hash=None,
    )
    instruction["command_hash"] = api().instruction_hash(instruction)
    lease["command_hash"] = instruction["command_hash"]
    return lease, instruction


class Device:
    def __init__(self, lease, instruction):
        self.lease, self.instruction = lease, instruction
        self.events = []
        self.ack_kind = "accepted_event_ids"
        self.fail_ack = False
        self.renew_count = 0

    async def next_lease(self):
        return {"lease": self.lease, "retry_after_seconds": 20}

    async def execution_command(self, identifier):
        assert identifier == self.lease["id"]
        return self.instruction

    async def renew_lease(self, identifier, boot, fence):
        self.renew_count += 1
        return self.lease

    async def report_events(self, events):
        self.events.extend(events)
        if self.fail_ack:
            raise OSError("isolated disconnect")
        ack = {
            k: []
            for k in (
                "accepted_event_ids",
                "duplicate_event_ids",
                "rejected_event_ids",
                "historical_event_ids",
            )
        }
        ack[self.ack_kind] = [e["event_id"] for e in events]
        if self.ack_kind == "historical_event_ids":
            ack["accepted_event_ids"] = [e["event_id"] for e in events]
        return ack | {"request_id": str(uuid4())}


class Adapter:
    def __init__(self):
        self.calls = 0
        self.closed = 0
        self.fail_send = False
        self.verified = True
        self.exclusive = True
        self.owned = True
        self.trace = []

    async def prepare(self, lease, instruction):
        self.trace.append("prepare")
        return api().PreparedProfile(self.owned, self.exclusive)

    async def validate(self, profile, lease, instruction):
        self.trace.append("validate")
        if not self.verified:
            raise api().ProbeError("CAPABILITY_UNVERIFIED")

    async def submit(self, profile, lease, instruction):
        self.trace.append("submit")
        self.calls += 1
        if self.fail_send:
            raise OSError("response lost")
        return ["isolated:evidence:1"]

    async def close(self, profile):
        self.closed += 1


def setup(tmp_path):
    m = api()
    lease, instruction = fixture_values()
    device = Device(lease, instruction)
    adapter = Adapter()
    spool = m.ExecutionSpool(tmp_path / "execution", str(uuid4()))
    runner = m.ExecutionConsumer(device, spool, str(uuid4()), adapter=adapter)
    return runner, device, adapter, spool


@pytest.mark.asyncio
async def test_intent_cloud_ack_precedes_single_send_and_second_delivery_never_resends(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    try:
        original = adapter.submit

        async def submit(*args):
            assert device.events[0]["phase"] == "WRITE_INTENT"
            assert spool.attempt(device.lease["attempt_id"])["state"] == "DISPATCH_STARTED"
            return await original(*args)

        adapter.submit = submit
        assert (await runner.run_once())["state"] == "VERIFYING"
        assert (await runner.run_once())["state"] == "UNKNOWN"
        assert adapter.calls == 1
        assert adapter.closed == 1
        assert device.events[-1]["phase"] == "SUBMITTED"
    finally:
        spool.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("ack", ["historical_event_ids", "rejected_event_ids"])
async def test_historical_or_rejected_intent_cannot_authorize_send(tmp_path, ack):
    runner, device, adapter, spool = setup(tmp_path)
    device.ack_kind = ack
    try:
        assert (await runner.run_once())["state"] == "UNKNOWN"
        assert adapter.calls == 0
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_ack_loss_and_restart_preserve_intent_and_never_send(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    device.fail_ack = True
    agent = spool.agent_id
    try:
        assert (await runner.run_once())["state"] == "UNKNOWN"
        original = spool.pending()[0]
    finally:
        spool.close()
    reopened = api().ExecutionSpool(tmp_path / "execution", agent)
    try:
        device.fail_ack = False
        again = api().ExecutionConsumer(device, reopened, str(uuid4()), adapter=adapter)
        assert (await again.run_once())["state"] == "UNKNOWN"
        assert adapter.calls == 0
        assert reopened.pending()[0] == original
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_send_response_loss_no_repeat_and_durable_unknown(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    adapter.fail_send = True
    try:
        assert (await runner.run_once())["state"] == "UNKNOWN"
        assert (await runner.run_once())["state"] == "UNKNOWN"
        assert adapter.calls == 1
        assert spool.attempt(device.lease["attempt_id"])["state"] == "UNKNOWN"
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_unverified_and_human_owned_profile_cannot_send(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    adapter.exclusive = False
    adapter.owned = False
    try:
        assert (await runner.run_once())["error_code"] == "PROFILE_BUSY"
        assert adapter.calls == 0 and adapter.closed == 0
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_unverified_capability_never_creates_intent(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    adapter.verified = False
    try:
        assert (await runner.run_once())["error_code"] == "CAPABILITY_UNVERIFIED"
        assert adapter.calls == 0
        assert len(device.events) == 1
        assert device.events[0]["phase"] == "PREFLIGHT"
        assert device.events[0]["state"] == "BLOCKED_AUTH"
        assert device.events[0]["error_code"] == "CAPABILITY_UNVERIFIED"
        assert device.events[0]["retryable"] is False
        assert (await runner.run_once())["state"] == "BLOCKED_AUTH"
        assert adapter.calls == 0
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_command_tamper_fails_before_profile_access(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    device.instruction["external_account_id"] = "456"
    try:
        assert (await runner.run_once())["error_code"] == "EXECUTION_COMMAND_INVALID"
        assert adapter.trace == []
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_default_adapter_closed_before_lease_poll(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    runner.adapter = None

    async def forbidden():
        raise AssertionError("should not claim")

    device.next_lease = forbidden
    try:
        assert (await runner.run_once())["error_code"] == "EXECUTION_ADAPTER_UNVERIFIED"
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_expiry_during_cloud_ack_prevents_send(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    original = device.report_events

    async def expire(events):
        ack = await original(events)
        device.lease["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        return ack

    device.report_events = expire
    try:
        assert (await runner.run_once())["state"] == "UNKNOWN"
        assert adapter.calls == 0
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_pending_events_replay_original_ids_without_adapter_calls(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    device.fail_ack = True
    try:
        await runner.run_once()
        pending = spool.pending()
        device.fail_ack = False
        device.ack_kind = "historical_event_ids"
        assert await runner.flush_history() == len(pending)
        assert spool.pending() == []
        assert adapter.calls == 0
        assert device.events[-len(pending) :] == pending
    finally:
        spool.close()


def test_spool_rejects_second_process_and_other_agent(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    try:
        with pytest.raises(api().ProbeError):
            api().ExecutionSpool(tmp_path / "execution", spool.agent_id)
    finally:
        spool.close()
    with pytest.raises(api().ProbeError):
        api().ExecutionSpool(tmp_path / "execution", str(uuid4()))


def test_spool_rejects_symlink_and_public_permissions(tmp_path):
    m = api()
    actual = tmp_path / "actual"
    actual.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)
    with pytest.raises(m.ProbeError):
        m.ExecutionSpool(linked, str(uuid4()))
    actual.chmod(0o755)
    with pytest.raises(m.ProbeError):
        m.ExecutionSpool(actual, str(uuid4()))


@pytest.mark.asyncio
async def test_submit_uncertainty_is_reported_as_unknown_not_failed(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    adapter.fail_send = True
    try:
        await runner.run_once()
        assert device.events[-1]["phase"] == "RECOVERY"
        assert device.events[-1]["state"] == "UNKNOWN"
        assert device.events[-1]["retryable"] is False
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_twenty_second_renewal_failure_prevents_delayed_submission(tmp_path):
    import asyncio

    runner, device, adapter, spool = setup(tmp_path)
    attempted = asyncio.Event()

    async def renew(*args):
        attempted.set()
        raise OSError("renew disconnected")

    async def prepare(*args):
        await asyncio.wait_for(attempted.wait(), 25)
        await asyncio.sleep(0)
        return api().PreparedProfile(True, True)

    adapter.prepare = prepare
    device.renew_lease = renew
    try:
        result = await runner.run_once()
        assert result["error_code"] == "EXECUTION_LEASE_EXPIRED"
        assert adapter.calls == 0
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_adapter_cannot_mutate_frozen_instruction_before_send(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    original = adapter.validate

    async def mutate(profile, lease, instruction):
        await original(profile, lease, instruction)
        instruction["external_account_id"] = "999"

    adapter.validate = mutate
    try:
        assert (await runner.run_once())["error_code"] == "EXECUTION_COMMAND_INVALID"
        assert adapter.calls == 0
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_cancellation_during_send_leaves_durable_nonrepeatable_intent(tmp_path):
    import asyncio

    runner, device, adapter, spool = setup(tmp_path)
    sending = asyncio.Event()

    async def submit(*args):
        adapter.calls += 1
        sending.set()
        await asyncio.Event().wait()

    adapter.submit = submit
    try:
        task = asyncio.create_task(runner.run_once())
        await asyncio.wait_for(sending.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert spool.attempt(device.lease["attempt_id"])["state"] == "DISPATCH_STARTED"
        assert (await runner.run_once())["state"] == "UNKNOWN"
        assert adapter.calls == 1
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_renewal_refreshes_server_instruction_deadline_beyond_initial_lease(
    tmp_path, monkeypatch
):
    import asyncio

    m = api()
    runner, device, adapter, spool = setup(tmp_path)
    clock = [datetime.now(UTC)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(m, "datetime", Clock)
    original_sleep = asyncio.sleep
    sixth = asyncio.Event()
    sleeps = [0]

    async def sleep(seconds):
        if seconds == 20:
            sleeps[0] += 1
            if sleeps[0] > 6:
                await asyncio.Event().wait()
            clock[0] += timedelta(seconds=20)
        await original_sleep(0)

    monkeypatch.setattr(m.asyncio, "sleep", sleep)
    commands = [0]

    async def command(identifier):
        commands[0] += 1
        return dict(device.instruction, allowed_until=device.lease["expires_at"])

    async def renew(*args):
        device.renew_count += 1
        device.lease = dict(
            device.lease, expires_at=(clock[0] + timedelta(seconds=120)).isoformat()
        )
        if device.renew_count == 6:
            asyncio.get_running_loop().call_soon(sixth.set)
        return device.lease

    async def prepare(*args):
        await asyncio.wait_for(sixth.wait(), 1)
        return m.PreparedProfile(True, True)

    device.execution_command = command
    device.renew_lease = renew
    adapter.prepare = prepare
    try:
        result = await runner.run_once()
        assert result["state"] == "VERIFYING"
        assert commands[0] == 7
        assert adapter.calls == 1
    finally:
        spool.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code", ["LOGIN_REQUIRED", "CHALLENGE", "IDENTITY_MISMATCH", "PROFILE_BUSY"]
)
async def test_preflight_human_challenge_is_persisted_and_reported_without_submit(tmp_path, code):
    runner, device, adapter, spool = setup(tmp_path)

    async def challenge(*args):
        raise api().ProbeError(code)

    adapter.validate = challenge
    try:
        result = await runner.run_once()
        assert result == {"state": "NEEDS_HUMAN", "error_code": code}
        assert adapter.calls == 0
        assert device.events[-1]["phase"] == "PREFLIGHT"
        assert device.events[-1]["state"] == "NEEDS_HUMAN"
        assert device.events[-1]["error_code"] == code
        assert spool.attempt(device.lease["attempt_id"])["state"] == "NEEDS_HUMAN"
        assert (await runner.run_once())["state"] == "NEEDS_HUMAN"
        assert adapter.calls == 0
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_renewed_instruction_tamper_revokes_submission(tmp_path, monkeypatch):
    import asyncio

    m = api()
    runner, device, adapter, spool = setup(tmp_path)
    original_sleep = asyncio.sleep
    refreshed = asyncio.Event()
    sleeps = [0]

    async def sleep(seconds):
        if seconds == 20:
            sleeps[0] += 1
            if sleeps[0] > 1:
                await asyncio.Event().wait()
        await original_sleep(0)

    monkeypatch.setattr(m.asyncio, "sleep", sleep)
    calls = [0]

    async def command(identifier):
        calls[0] += 1
        if calls[0] > 1:
            refreshed.set()
            return dict(device.instruction, external_account_id="999")
        return device.instruction

    async def prepare(*args):
        await asyncio.wait_for(refreshed.wait(), 1)
        return m.PreparedProfile(True, True)

    device.execution_command = command
    adapter.prepare = prepare
    try:
        result = await runner.run_once()
        assert result["error_code"] == "EXECUTION_LEASE_EXPIRED"
        assert adapter.calls == 0
        assert device.events == []
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_challenge_after_intent_stays_unknown_and_never_retries(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)
    calls = [0]

    async def validate(*args):
        calls[0] += 1
        if calls[0] == 2:
            raise api().ProbeError("CHALLENGE")

    adapter.validate = validate
    try:
        assert (await runner.run_once())["state"] == "UNKNOWN"
        assert device.events[-1]["phase"] == "RECOVERY"
        assert device.events[-1]["state"] == "UNKNOWN"
        assert adapter.calls == 0
        assert (await runner.run_once())["state"] == "UNKNOWN"
    finally:
        spool.close()


@pytest.mark.asyncio
async def test_arbitrary_preflight_exception_does_not_claim_platform_failure(tmp_path):
    runner, device, adapter, spool = setup(tmp_path)

    async def failure(*args):
        raise RuntimeError("arbitrary adapter error")

    adapter.validate = failure
    try:
        result = await runner.run_once()
        assert result == {"state": "BLOCKED_AUTH", "error_code": "EXECUTION_CONNECTION_FAILED"}
        assert device.events == []
        assert adapter.calls == 0
    finally:
        spool.close()
