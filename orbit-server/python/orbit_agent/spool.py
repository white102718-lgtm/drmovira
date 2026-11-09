"""只读监测SQLite WAL/FULL spool；未ACK原载荷保留，重启新boot不冒充旧状态。"""

import fcntl
import json
import os
import sqlite3
import stat
from pathlib import Path
from uuid import uuid4

from orbit_agent.adspower_status import ProbeError
from orbit_agent.protocol import integer, uuid, validate_payload


class Spool:
    def __init__(self, directory, agent_id, *, ack_history=1000, retired_history=2000):
        for limit in (ack_history, retired_history):
            if type(limit) is not int or not 1 <= limit <= 10000:
                raise ProbeError("SPOOL_LIMIT_REJECTED")
        self.ack_history = ack_history
        self.retired_history = retired_history
        self.agent_id = uuid(agent_id)
        self.lock_fd = None
        self.connection = None
        root = Path(directory)
        try:
            if not root.is_absolute():
                raise ProbeError("SPOOL_PATH_REJECTED")
            root.mkdir(mode=0o700, parents=False, exist_ok=True)
            info = root.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
            ):
                raise ProbeError("SPOOL_PATH_REJECTED")
            self.lock_fd = os.open(
                root / "owner.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
            )
            self._private_file(os.fstat(self.lock_fd))
            self._same_file(os.fstat(self.lock_fd), (root / "owner.lock").lstat())
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            db = root / "monitor.sqlite3"
            fd = os.open(db, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            info = os.fstat(fd)
            os.close(fd)
            self._private_file(info)
            for suffix in ("-wal", "-shm", "-journal"):
                side = root / ("monitor.sqlite3" + suffix)
                if side.exists() or side.is_symlink():
                    self._private_file(side.lstat())
            self.connection = sqlite3.connect(db)
            self._same_file(info, db.lstat())
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
            page_size = self.connection.execute("PRAGMA page_size").fetchone()[0]
            maximum_pages = 128 * 1024 * 1024 // page_size
            if self.connection.execute("PRAGMA page_count").fetchone()[0] > maximum_pages:
                raise ProbeError("SPOOL_FULL")
            self.connection.execute(f"PRAGMA max_page_count={maximum_pages}")
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(agent_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS boot(id TEXT PRIMARY KEY,seq INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,boot TEXT NOT NULL,kind TEXT NOT NULL,
                  payload TEXT NOT NULL,ack INTEGER NOT NULL DEFAULT 0);
            """)
            prior = self.connection.execute("SELECT agent_id FROM metadata").fetchall()
            if prior and prior != [(agent_id,)]:
                raise ProbeError("SPOOL_AGENT_MISMATCH")
            self.boot_id = str(uuid4())
            with self.connection:
                self.connection.execute("INSERT OR IGNORE INTO metadata VALUES(?)", (agent_id,))
                self.connection.execute("INSERT INTO boot VALUES(?,0)", (self.boot_id,))
                self._prune_acknowledged()
        except (OSError, sqlite3.Error):
            self.close()
            raise ProbeError("SPOOL_UNAVAILABLE") from None
        except ProbeError:
            self.close()
            raise

    def append(self, kind, payload):
        try:
            with self.connection:
                self.connection.execute("BEGIN IMMEDIATE")
                retired = self.connection.execute(
                    "SELECT COUNT(*) FROM outbox WHERE ack<>1 AND (boot<>? OR ack=-1)",
                    (self.boot_id,),
                ).fetchone()[0]
                if retired >= self.retired_history:
                    raise ProbeError("SPOOL_RETIRED_HISTORY_FULL")
                active = self.connection.execute(
                    "SELECT COUNT(*) FROM outbox WHERE ack=0 AND boot=?", (self.boot_id,)
                ).fetchone()[0]
                if active >= 10000:
                    raise ProbeError("SPOOL_FULL")
                value = dict(payload) | {"agent_id": self.agent_id, "boot_id": self.boot_id}
                if kind == "heartbeat":
                    seq = (
                        self.connection.execute(
                            "SELECT seq FROM boot WHERE id=?", (self.boot_id,)
                        ).fetchone()[0]
                        + 1
                    )
                    integer(seq)
                    value["seq"] = seq
                validate_payload(kind, value)
                raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                if len(raw.encode()) > 2 * 1024 * 1024:
                    raise ProbeError("SPOOL_PAYLOAD_TOO_LARGE")
                size = len(raw.encode())
                while (
                    self.connection.execute(
                        "SELECT COALESCE(SUM(length(CAST(payload AS BLOB))),0) FROM outbox"
                    ).fetchone()[0]
                    + size
                    > 64 * 1024 * 1024
                ):
                    deleted = self.connection.execute(
                        "DELETE FROM outbox WHERE id=(SELECT MIN(id) FROM outbox WHERE ack=1)"
                    ).rowcount
                    if not deleted:
                        raise ProbeError("SPOOL_FULL")
                if kind == "heartbeat":
                    self.connection.execute("UPDATE boot SET seq=? WHERE id=?", (seq, self.boot_id))
                cursor = self.connection.execute(
                    "INSERT INTO outbox(boot,kind,payload) VALUES(?,?,?)", (self.boot_id, kind, raw)
                )
                return {"local_id": cursor.lastrowid, "kind": kind, "payload": json.loads(raw)}
        except sqlite3.Error:
            raise ProbeError("SPOOL_UNAVAILABLE") from None

    def pending(self):
        found = self.connection.execute(
            "SELECT id,kind,payload FROM outbox WHERE boot=? AND ack=0 ORDER BY id LIMIT 200",
            (self.boot_id,),
        ).fetchall()
        return [{"local_id": i, "kind": kind, "payload": json.loads(raw)} for i, kind, raw in found]

    def unacknowledged_count(self):
        return self.connection.execute("SELECT COUNT(*) FROM outbox WHERE ack<>1").fetchone()[0]

    def ack(self, local_id):
        with self.connection:
            self.connection.execute(
                "UPDATE outbox SET ack=1 WHERE id=? AND boot=? AND ack=0",
                (local_id, self.boot_id),
            )
            self._prune_acknowledged()
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def reject(self, local_id):
        """保留明确拒绝的原载荷作本机历史，ack=-1不是云端ACK。"""
        with self.connection:
            self.connection.execute(
                "UPDATE outbox SET ack=-1 WHERE id=? AND boot=? AND ack=0",
                (local_id, self.boot_id),
            )

    def purge_retired(self, *, through_local_id):
        """显式运维删除旧 boot 历史；不是 ACK，不触碰本轮待确认载荷。"""
        if type(through_local_id) is not int or through_local_id < 1:
            raise ProbeError("SPOOL_LIMIT_REJECTED")
        with self.connection:
            count = self.connection.execute(
                "DELETE FROM outbox WHERE boot<>? AND id<=?",
                (self.boot_id, through_local_id),
            ).rowcount
            self._prune_acknowledged()
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return count

    def _prune_acknowledged(self):
        self.connection.execute(
            "DELETE FROM outbox WHERE ack=1 AND id NOT IN "
            "(SELECT id FROM outbox WHERE ack=1 ORDER BY id DESC LIMIT ?)",
            (self.ack_history,),
        )
        self.connection.execute(
            "DELETE FROM boot WHERE id<>? AND NOT EXISTS "
            "(SELECT 1 FROM outbox WHERE outbox.boot=boot.id)",
            (self.boot_id,),
        )

    @staticmethod
    def _private_file(info):
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
        ):
            raise ProbeError("SPOOL_PATH_REJECTED")

    @staticmethod
    def _same_file(opened, current):
        Spool._private_file(current)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise ProbeError("SPOOL_PATH_REJECTED")

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
