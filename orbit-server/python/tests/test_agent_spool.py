"""只读Agent spool不丢原请求，不把内存重试当持久性。"""

from uuid import UUID

import pytest


def test_restart_retains_unacked_payload_and_new_boot_sequence(tmp_path):
    from orbit_agent.spool import Spool

    root = tmp_path / "private"
    with Spool(root, str(UUID(int=1))) as spool:
        old = spool.boot_id
        event = spool.append("heartbeat", {"profiles": [], "observed_at": "2026-11-09T01:00:00Z"})
        assert event["payload"]["seq"] == 1
        assert spool.pending()[0] == event
    with Spool(root, str(UUID(int=1))) as spool:
        assert spool.boot_id != old
        assert spool.pending() == []
        assert spool.unacknowledged_count() == 1
        event = spool.append("heartbeat", {"profiles": [], "observed_at": "2026-11-09T01:00:15Z"})
        assert event["payload"]["seq"] == 1
        spool.ack(event["local_id"])
        assert spool.pending() == [] and spool.unacknowledged_count() == 1


def test_identity_and_unknown_fields_cannot_enter_spool(tmp_path):
    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.spool import Spool

    with Spool(tmp_path / "private", str(UUID(int=1))) as spool:
        with pytest.raises(ProbeError):
            spool.append("heartbeat", {"profiles": [], "observed_at": "x", "cookie": "private"})
        assert spool.pending() == []


def test_private_directory_and_single_owner(tmp_path):
    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.spool import Spool

    root = tmp_path / "private"
    with Spool(root, str(UUID(int=1))):
        assert root.stat().st_mode & 0o077 == 0
        with pytest.raises(ProbeError):
            Spool(root, str(UUID(int=1)))
    root.chmod(0o755)
    with pytest.raises(ProbeError):
        Spool(root, str(UUID(int=1)))


def test_ack_history_is_bounded_without_deleting_unacked(tmp_path):
    from orbit_agent.spool import Spool

    body = {"profiles": [], "observed_at": "2026-11-09T00:00:00Z"}
    with Spool(tmp_path / "private", str(UUID(int=1)), ack_history=2) as spool:
        pending = spool.append("heartbeat", body)
        for _ in range(5):
            value = spool.append("heartbeat", body)
            spool.ack(value["local_id"])
        assert (
            spool.connection.execute("SELECT COUNT(*) FROM outbox WHERE ack=1").fetchone()[0] == 2
        )
        assert spool.pending() == [pending]
        spool.reject(pending["local_id"])
        spool.ack(pending["local_id"])
        status = spool.connection.execute(
            "SELECT ack FROM outbox WHERE id=?", (pending["local_id"],)
        ).fetchone()[0]
        assert status == -1
        page_size = spool.connection.execute("PRAGMA page_size").fetchone()[0]
        max_pages = spool.connection.execute("PRAGMA max_page_count").fetchone()[0]
        assert page_size * max_pages == 128 * 1024 * 1024


def test_retired_quota_explicit_purge_never_marks_ack_and_preserves_current(tmp_path):
    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.spool import Spool

    root = tmp_path / "private"
    body = {"profiles": [], "observed_at": "2026-11-09T00:00:00Z"}
    with Spool(root, str(UUID(int=1)), retired_history=1) as spool:
        old = spool.append("heartbeat", body)
    with Spool(root, str(UUID(int=1)), retired_history=1) as spool:
        with pytest.raises(ProbeError) as caught:
            spool.append("heartbeat", body)
        assert caught.value.code == "SPOOL_RETIRED_HISTORY_FULL"
        assert spool.purge_retired(through_local_id=old["local_id"]) == 1
        current = spool.append("heartbeat", body)
        assert spool.purge_retired(through_local_id=current["local_id"]) == 0
        assert spool.pending() == [current]


@pytest.mark.parametrize("filename", ["owner.lock", "monitor.sqlite3", "monitor.sqlite3-wal"])
def test_rejects_hardlinked_lock_or_database(tmp_path, filename):
    import os

    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.spool import Spool

    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    source = tmp_path / "elsewhere"
    source.write_text("")
    source.chmod(0o600)
    os.link(source, root / filename)
    with pytest.raises(ProbeError):
        Spool(root, str(UUID(int=1)))
