"""本机只读监测CLI：一次/N轮/15秒常驻；未知结果从原SQLite载荷重放。"""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from orbit_agent.adspower_readonly import ReadonlyAdsPower
from orbit_agent.adspower_status import DEFAULT_ENDPOINT, ProbeError
from orbit_agent.discovery_cache import BackgroundDiscovery
from orbit_agent.meta_dom_probe import inspect_existing_page, observe_existing_pages
from orbit_agent.meta_dom_v2 import classify_pages
from orbit_agent.protocol import ADAPTER_VERSION, profile_id
from orbit_agent.spool import Spool
from orbit_agent.transport import DeviceClient, DeviceRejected


def now():
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def unknown(reason):
    return {
        "identity_state": "UNKNOWN",
        "external_account_id": None,
        "currency": None,
        "reason": reason,
        "evidence_sha256": hashlib.sha256(reason.encode()).hexdigest(),
    }


async def flush(device, spool, *, budget_seconds=8):
    """只在精确ACK后标已送达；明确永久拒绝保留原行，不能当ACK丢弃。"""
    blocked = False
    deadline = asyncio.get_running_loop().time() + budget_seconds
    for event in spool.pending():
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return False
        try:
            async with asyncio.timeout(remaining):
                await device.send(event["kind"], event["payload"])
            spool.ack(event["local_id"])
        except DeviceRejected as error:
            if error.status in {400, 403, 404, 409, 410, 422}:
                spool.reject(event["local_id"])
                if event["kind"] == "heartbeat":
                    raise ProbeError(error.code) from None
            else:
                blocked = True
                break
        except (ProbeError, TimeoutError):
            blocked = True
            break
    return not blocked


async def run_cycle(adapter, device, spool, *, selected_profiles):
    if not await flush(device, spool):
        return {"delivery": "PENDING", "error_code": "DEVICE_CONNECTION_FAILED"}
    config = await device.configuration()
    snapshot = await adapter.discover()
    observed = now()
    profiles = [
        {
            "id": str(uuid5(UUID(spool.agent_id), external)),
            "agent_id": spool.agent_id,
            "external_profile_id": external,
            "process_state": state,
            "identity_state": "UNKNOWN",
            "account_ids": [],
            "observed_at": snapshot.observed_at,
        }
        for external, state in snapshot.profiles
    ]
    event = spool.append("heartbeat", {"profiles": profiles, "observed_at": observed})
    try:
        ack = await device.send("heartbeat", event["payload"])
    except ProbeError:
        return snapshot.summary() | {
            "delivery": "PENDING",
            "error_code": "DEVICE_CONNECTION_FAILED",
        }
    spool.ack(event["local_id"])
    seq = event["payload"]["seq"]
    spool.append(
        "diagnostics",
        {
            "seq": seq,
            "observed_at": observed,
            "api_status": snapshot.api_status,
            "inventory_coverage": snapshot.coverage,
            "error_code": snapshot.error_code,
        },
    )
    reports = 0
    deferred = 0
    identity_deadline = asyncio.get_running_loop().time() + 12
    # READY需要两个连续新心跳；首个SUSPECT不制造可被误认已核验的身份报告。
    if ack["state"] == "READY":
        observed_profiles = {external for external, _ in snapshot.profiles}
        cache = {}
        eligible = [
            binding
            for binding in config["bindings"]
            if binding["profile_external_id"] in selected_profiles
            and binding["profile_external_id"] in observed_profiles
        ]
        if eligible:
            offset = ((seq - 1) * 100) % len(eligible)
            eligible = eligible[offset:] + eligible[:offset]
        deferred = max(0, len(eligible) - 100)
        deadline = asyncio.get_running_loop().time() + 8
        for binding in eligible[:100]:
            if asyncio.get_running_loop().time() >= identity_deadline:
                deferred = len(eligible) - reports
                break
            external = binding["profile_external_id"]
            if external not in cache:
                endpoint = snapshot.selected_cdp(external)
                cache[external] = "CDP_UNAVAILABLE"
                remaining = deadline - asyncio.get_running_loop().time()
                if endpoint and remaining > 0:
                    try:
                        async with asyncio.timeout(remaining):
                            cache[external] = await observe_existing_pages(endpoint)
                    except ProbeError as error:
                        cache[external] = error.code
                    except TimeoutError:
                        cache[external] = "IDENTITY_PROBE_FAILED"
            facts = cache[external]
            result = (
                unknown(facts)
                if type(facts) is str
                else classify_pages(facts, binding["external_account_id"], binding["currency"])
            )
            spool.append(
                "identity",
                {
                    "seq": seq,
                    "event_id": str(uuid4()),
                    "binding_id": binding["id"],
                    "binding_revision": binding["revision"],
                    "profile_external_id": external,
                    "external_account_id": result["external_account_id"],
                    "currency": result["currency"],
                    "identity_state": result["identity_state"],
                    "adapter_version": ADAPTER_VERSION,
                    "observed_at": now(),
                    "evidence_sha256": result["evidence_sha256"],
                },
            )
            reports += 1
    await flush(
        device,
        spool,
        budget_seconds=max(0, min(8, identity_deadline - asyncio.get_running_loop().time())),
    )
    return snapshot.summary() | {
        "delivery": "PENDING" if spool.pending() else "ACKNOWLEDGED",
        "monitor_state": ack["state"],
        "identity_report_count": reports,
        "identity_report_deferred_count": deferred,
    }


async def collect_only(adapter, selected_profiles):
    snapshot = await adapter.discover()
    states = []
    reasons = []
    for external in sorted(selected_profiles):
        endpoint = snapshot.selected_cdp(external)
        result = unknown("CDP_UNAVAILABLE")
        if endpoint:
            try:
                result = await inspect_existing_page(endpoint, None, None)
            except ProbeError as error:
                result = unknown(error.code)
        states.append(result["identity_state"])
        reasons.append(result["reason"])
    # 标识、名称、路径、CDP地址和DOM不进入stdout。原始可见文本也不落盘。
    return snapshot.summary() | {
        "mode": "COLLECT_ONLY",
        "identity_states": states,
        "identity_reasons": reasons,
        "execution_capability": "UNVERIFIED",
    }


async def run(args):
    selected = {profile_id(value) for value in args.profile_id}
    if len(selected) > 20:
        raise ProbeError("PROFILE_SELECTION_TOO_LARGE")
    adapter = ReadonlyAdsPower(
        args.endpoint, api_key_file=args.api_key_file, allowed_ports={50325, *args.allow_port}
    )
    count = 0
    spool = None
    background = None
    try:
        if not args.collect_only:
            if not all(
                (
                    args.device_origin,
                    args.agent_id,
                    args.ca_file,
                    args.certificate,
                    args.key_file,
                    args.spool_dir,
                )
            ):
                raise ProbeError("DEVICE_CONFIGURATION_REQUIRED")
            device = DeviceClient(
                args.device_origin,
                args.agent_id,
                ca_file=args.ca_file,
                certificate=args.certificate,
                key_file=args.key_file,
            )
            spool = Spool(args.spool_dir, args.agent_id)
            background = BackgroundDiscovery(adapter)
        while args.forever or count < args.iterations:
            started = asyncio.get_running_loop().time()
            try:
                result = (
                    await collect_only(adapter, selected)
                    if args.collect_only
                    else await run_cycle(background, device, spool, selected_profiles=selected)
                )
            except ProbeError as error:
                result = {"error_code": error.code, "delivery": "PENDING"}
            print(json.dumps(result, ensure_ascii=False), flush=True)
            count += 1
            if not args.forever and count >= args.iterations:
                break
            await asyncio.sleep(max(0, 15 - (asyncio.get_running_loop().time() - started)))
    finally:
        if background:
            await background.close()
        if spool:
            spool.close()
    if args.collect_only:
        return 0 if result.get("api_status") == "READY" else 1
    return 0 if result.get("delivery") == "ACKNOWLEDGED" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="执行机只读发现/现有页面观察/主动mTLS监测")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--allow-port", type=int, action="append", default=[])
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--profile-id", action="append", default=[])
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--device-origin")
    parser.add_argument("--agent-id")
    for name in ("ca-file", "certificate", "key-file", "spool-dir"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.iterations <= 1000:
        parser.error("固定验收轮数必须为1至1000")
    try:
        return asyncio.run(run(args))
    except ProbeError as error:
        print(json.dumps({"error_code": error.code}), flush=True)
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
