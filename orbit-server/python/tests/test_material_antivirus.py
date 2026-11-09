"""病毒扫描协议负例纯测；协议夹具不是实际病毒引擎验收。"""

import hashlib
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from orbit_api import material_antivirus as module

VERSION = b"ClamAV 1.5.4/28177/Sun Nov 08 14:23:52 2026\0"


def policy(**changes):
    return replace(
        module.ClamdPolicy(
            port=19310,
            engine_version="1.5.4",
            daily_db_version=28177,
            daily_db_built_at=datetime.now(UTC) - timedelta(hours=1),
            config_sha256="a" * 64,
            max_file_bytes=600 * 1024**2,
            max_scan_bytes=1000 * 1024**2,
            stream_max_bytes=600 * 1024**2,
            alert_exceeds_max=True,
        ),
        **changes,
    )


class Connection:
    def __init__(self, reply):
        self.reply, self.sent, self.timeouts = reply, [], []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, limit):
        result, self.reply = self.reply[:3], self.reply[3:]
        return result


@pytest.fixture
def run_scan(tmp_path, monkeypatch):
    source = tmp_path / "original"
    source.write_bytes(b"safe-media-protocol-fixture")
    objects = SimpleNamespace(
        original=lambda *args: source,
        mutation_guard=lambda *args: nullcontext(),
    )
    sha = hashlib.sha256(source.read_bytes()).hexdigest()

    def run(
        reply=b"stream: OK\0",
        *,
        configured=None,
        post=VERSION,
        expected_sha=sha,
        expected_size=None,
    ):
        connections = [Connection(VERSION), Connection(reply), Connection(post)]
        pending = list(connections)
        monkeypatch.setattr(
            module.socket, "create_connection", lambda *args, **kwargs: pending.pop(0)
        )
        receipt = module.ClamdMaterialScanner(configured or policy()).scan(
            objects,
            "tenant",
            "upload",
            expected_sha,
            len(source.read_bytes()) if expected_size is None else expected_size,
        )
        return receipt, connections

    return run


def test_clean_requires_complete_stream_hash_both_versions_and_framed_unique_reply(run_scan):
    receipt, connections = run_scan()
    assert receipt.result == "CLEAN" and receipt.error_code is None
    assert receipt.engine_version == "1.5.4" and receipt.database_version == 28177
    assert connections[0].sent == [b"zVERSION\0"]
    assert connections[1].sent[0] == b"zINSTREAM\0"
    assert connections[1].sent[-1] == b"\0\0\0\0"
    assert connections[2].sent == [b"zVERSION\0"]
    assert all(0 < timeout <= 10 for connection in connections for timeout in connection.timeouts)


@pytest.mark.parametrize(
    "reply",
    [
        b"stream: OK",
        b"",
        b"stream: OK\0stream: OK\0",
        b"stream: OK\0garbage",
        b"stream: ERROR\0",
        b"INSTREAM size limit exceeded. ERROR\0",
        b"UNKNOWN COMMAND\0",
        b"x" * 8193 + b"\0",
        b"stream: UNKNOWN\0",
        b"stream: \n FOUND\0",
    ],
)
def test_unknown_or_incomplete_or_multiple_result_never_clean(run_scan, reply):
    receipt, _ = run_scan(reply)
    assert receipt.result == "UNVERIFIED" and receipt.error_code == "ANTIVIRUS_PROTOCOL_INVALID"


def test_found_is_infected_but_limit_heuristic_is_unverified(run_scan):
    infected, _ = run_scan(b"stream: harmless-test-signature FOUND\0")
    assert infected.result == "INFECTED" and infected.error_code == "ANTIVIRUS_INFECTED"
    limited, _ = run_scan(b"stream: Heuristics.Limits.Exceeded.MaxFileSize FOUND\0")
    assert limited.result == "UNVERIFIED" and limited.error_code == "ANTIVIRUS_LIMIT_EXCEEDED"


@pytest.mark.parametrize(
    "changes",
    [
        {"host": "example.com"},
        {"port": True},
        {"max_file_bytes": 100 * 1024**2},
        {"stream_max_bytes": 100 * 1024**2},
        {"max_scan_bytes": 500 * 1024**2},
        {"alert_exceeds_max": False},
        {"deadline_seconds": 151},
        {"config_sha256": "unknown"},
        {"max_db_age_seconds": 999999},
    ],
)
def test_unattested_or_inadequate_configuration_never_connects(run_scan, changes):
    receipt, connections = run_scan(configured=policy(**changes))
    assert receipt.result == "UNVERIFIED" and receipt.error_code == "ANTIVIRUS_POLICY_UNVERIFIED"
    assert all(not connection.sent for connection in connections)
    assert receipt.engine_version is None


@pytest.mark.parametrize(
    "built,code",
    [
        (datetime.now(UTC) - timedelta(days=3), "ANTIVIRUS_DATABASE_STALE"),
        (datetime.now(UTC) + timedelta(days=1), "ANTIVIRUS_DATABASE_STALE"),
        (datetime.now(), "ANTIVIRUS_DATABASE_UNVERIFIED"),
    ],
)
def test_database_age_uses_trusted_aware_build_time(run_scan, built, code):
    receipt, connections = run_scan(configured=policy(daily_db_built_at=built))
    assert receipt.result == "UNVERIFIED" and receipt.error_code == code
    assert all(not connection.sent for connection in connections)


@pytest.mark.parametrize(
    "post",
    [
        b"ClamAV 1.5.4/28178/changed\0",
        b"ClamAV 1.5.5/28177/changed\0",
        b"COMMAND UNAVAILABLE\0",
    ],
)
def test_engine_or_database_changed_after_scan_cancels_clean(run_scan, post):
    receipt, _ = run_scan(post=post)
    assert receipt.result == "UNVERIFIED" and receipt.error_code == "ANTIVIRUS_VERSION_CHANGED"


def test_object_bytes_must_match_frozen_original_hash_and_size(run_scan):
    for kwargs in ({"expected_sha": "b" * 64}, {"expected_size": 1}, {"expected_size": 1000}):
        receipt, _ = run_scan(**kwargs)
        assert receipt.result == "UNVERIFIED" and receipt.error_code == "ANTIVIRUS_OBJECT_CHANGED"


def test_missing_scanner_never_has_clean_default():
    receipt = module.UnavailableMaterialScanner().scan(None, "tenant", "upload", "a" * 64, 100)
    assert receipt.result == "UNVERIFIED" and receipt.error_code == "ANTIVIRUS_UNAVAILABLE"
    assert receipt.engine_version is None and receipt.database_version is None


def test_absolute_deadline_applies_even_while_server_sends_small_records(monkeypatch):
    scanner = module.ClamdMaterialScanner(policy())
    connection = Connection(b"x" * 100)
    ticks = iter(range(100))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    with pytest.raises(module.OrbitError) as error:
        scanner._record(connection, 3)
    assert error.value.code == "ANTIVIRUS_TIMEOUT"
