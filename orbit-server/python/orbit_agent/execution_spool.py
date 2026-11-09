"""广告提交的独立私有SQLite日志；意图和发送占位先落盘，崩溃后不能重放点击。"""

import fcntl
import json
import os
import sqlite3
import stat
from pathlib import Path

from orbit_agent.adspower_status import ProbeError
from orbit_agent.protocol import uuid


class ExecutionSpool:
    """单进程所有权，WAL/FULL；未确认事件不删除，满额时禁止新执行。"""

    def __init__(self, directory, agent_id):
        self.agent_id = uuid(agent_id)
        self.connection = None
        self.lock_fd = None
        try:
            root = Path(directory)
            if not root.is_absolute():
                raise ValueError
            root.mkdir(mode=0o700, parents=False, exist_ok=True)
            info = root.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
            ):
                raise ValueError
            self.lock_fd = os.open(
                root / "owner.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            )
            lock_info = os.fstat(self.lock_fd)
            self._private(lock_info)
            path_info = (root / "owner.lock").lstat()
            if (lock_info.st_dev, lock_info.st_ino) != (path_info.st_dev, path_info.st_ino):
                raise ValueError
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            db = root / "execution.sqlite3"
            fd = os.open(db, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                original = os.fstat(fd)
                self._private(original)
            finally:
                os.close(fd)
            for suffix in ("-wal", "-shm", "-journal"):
                path = root / ("execution.sqlite3" + suffix)
                if path.exists() or path.is_symlink():
                    self._private(path.lstat())
            self.connection = sqlite3.connect(db)
            self.connection.row_factory = sqlite3.Row
            current = db.lstat()
            if (original.st_dev, original.st_ino) != (current.st_dev, current.st_ino):
                raise ValueError
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
            self.connection.execute("PRAGMA max_page_count=32768")
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS owner(agent TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS attempts(
                  id TEXT PRIMARY KEY,lease TEXT NOT NULL,command_hash TEXT NOT NULL,
                  state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                  id TEXT PRIMARY KEY,attempt TEXT NOT NULL,sequence INTEGER NOT NULL,
                  payload TEXT NOT NULL,ack INTEGER NOT NULL DEFAULT 0,
                  UNIQUE(attempt,sequence));
            """)
            owner = self.connection.execute("SELECT agent FROM owner").fetchone()
            if owner is not None and owner["agent"] != self.agent_id:
                raise ValueError
            with self.connection:
                self.connection.execute("INSERT OR IGNORE INTO owner VALUES(?)", (self.agent_id,))
        except (OSError, ValueError, sqlite3.Error):
            self.close()
            raise ProbeError("EXECUTION_SPOOL_UNAVAILABLE") from None

    @staticmethod
    def _private(info):
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError

    def attempt(self, identifier):
        row = self.connection.execute("SELECT * FROM attempts WHERE id=?", (identifier,)).fetchone()
        return dict(row) if row else None

    def begin(self, lease):
        """同attempt只创建一次；旧记录即使未发送也必须先恢复核验。"""
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            if self.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] >= 10000:
                raise ProbeError("EXECUTION_SPOOL_FULL")
            if self.attempt(lease["attempt_id"]) is not None:
                return False
            self.connection.execute(
                "INSERT INTO attempts VALUES(?,?,?,?)",
                (
                    lease["attempt_id"],
                    json.dumps(lease, sort_keys=True),
                    lease["command_hash"],
                    "PREPARING",
                ),
            )
            return True

    def record(self, attempt, event, state):
        raw = json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(raw.encode()) > 16384:
            raise ProbeError("EXECUTION_EVENT_INVALID")
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            if self.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] >= 30000:
                raise ProbeError("EXECUTION_SPOOL_FULL")
            self.connection.execute(
                "INSERT INTO events VALUES(?,?,?,?,0)",
                (event["event_id"], attempt, event["sequence"], raw),
            )
            self.connection.execute("UPDATE attempts SET state=? WHERE id=?", (state, attempt))
        return event

    def acknowledge(self, event):
        with self.connection:
            self.connection.execute("UPDATE events SET ack=1 WHERE id=?", (event["event_id"],))

    def dispatch(self, attempt, intent):
        """仅本地已持久且已云确认的意图能占用一次发送权；事务提交后才调用Adapter。"""
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute(
                "SELECT ack,attempt FROM events WHERE id=?", (intent["event_id"],)
            ).fetchone()
            if row is None or row["ack"] != 1 or row["attempt"] != attempt:
                raise ProbeError("EXECUTION_INTENT_UNCONFIRMED")
            changed = self.connection.execute(
                "UPDATE attempts SET state='DISPATCH_STARTED' WHERE id=? AND state='WRITE_INTENT'",
                (attempt,),
            ).rowcount
            if changed != 1:
                raise ProbeError("EXECUTION_ALREADY_STARTED")

    def next_sequence(self, attempt):
        return self.connection.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE attempt=?", (attempt,)
        ).fetchone()[0]

    def state(self, attempt, state):
        with self.connection:
            self.connection.execute("UPDATE attempts SET state=? WHERE id=?", (state, attempt))

    def pending(self):
        return [
            json.loads(row["payload"])
            for row in self.connection.execute(
                "SELECT payload FROM events WHERE ack=0 ORDER BY rowid LIMIT 100"
            )
        ]

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
