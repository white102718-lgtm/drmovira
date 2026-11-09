"""边界工具安全指标与精确时间换算纯测，不代替真实MySQL/SSE。"""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from task_event_boundary_checks import (  # noqa: E402
    TRANSACTION_SQL,
    TransactionObservation,
    epoch_seconds,
)


def row(identifier, locks=0):
    return (identifier, 11, "RUNNING", True, locks, 1)


def test_sleep_connections_are_not_counted_as_long_transactions():
    observation = TransactionObservation()
    observation.add([], 0)
    observation.add([], 100)
    assert observation.longest == 0 and observation.samples == 2


def test_different_short_transactions_and_disappeared_id_do_not_accumulate_age():
    observation = TransactionObservation()
    observation.add([row("a", 3)], 0)
    observation.add([row("a")], 0.9)
    observation.add([row("b", 5)], 5)
    observation.add([], 9)
    observation.add([row("a")], 10)
    assert observation.longest == 0.9
    assert observation.maximum_rows_locked == 5


def test_same_transaction_beyond_one_second_fails_instead_of_reporting_green():
    observation = TransactionObservation()
    observation.add([row("still-open")], 1.0)
    with pytest.raises(AssertionError):
        observation.add([row("still-open")], 2.001)


@pytest.mark.parametrize(
    "microsecond,expected",
    [
        (0, "1794096000"),
        (1000, "1794096000.001"),
        (999000, "1794096000.999"),
        (123000, "1794096000.123"),
    ],
)
def test_database_utc_millisecond_mapping_uses_decimal(microsecond, expected):
    # 2026-11-08 00:00Z，结果不依赖本机Asia/Shanghai时区。
    assert epoch_seconds(datetime(2026, 11, 8, microsecond=microsecond)) == Decimal(expected)


def test_observation_query_never_selects_sql_text_or_other_database_rows():
    assert "p.DB=%s" in TRANSACTION_SQL
    assert "p.ID<>CONNECTION_ID()" in TRANSACTION_SQL
    assert "t.trx_query IS NULL" in TRANSACTION_SQL
    assert "t.trx_rows_locked" in TRANSACTION_SQL
    assert "SHOW PROCESSLIST" not in TRANSACTION_SQL
