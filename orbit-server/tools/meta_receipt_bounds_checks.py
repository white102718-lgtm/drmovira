"""051回执CHECK真实矩阵；仅由主线串行执行，所有探针行最终rollback。"""

import hashlib
import json
import re
from copy import deepcopy
from uuid import uuid4

META_RECEIPT_BOUNDS_CASES = [
    "pythonMetaReceiptNativeNumericFourValidBoundaryCombinations",
    "pythonMetaReceiptMissingNullTypeAndRangeMatrixRejectsExact3819WithoutWarnings",
    "pythonMetaReceiptExistingCompleteLedgerNoopAndRollbackKeepSixTables",
]
TABLES = (
    "orbit_meta_raw_head",
    "orbit_meta_raw_account",
    "orbit_meta_raw_resource",
    "orbit_meta_raw_idempotency",
    "orbit_meta_raw_audit",
    "orbit_meta_raw_outbox",
)


def guard_meta_receipt_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not isinstance(database, str)
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("回执边界专项仅允许13306本轮UUID库")
    # 不接管调用者已有事务，避免探针finally rollback误撤其他修改。
    if getattr(admin, "server_status", 0) & 1:
        raise ValueError("回执边界专项需要无在途事务的独占管理连接")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("实际数据库不是本轮UUID隔离库")


def encode(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def receipt_probes(base):
    """只构造有界SQL技术探针，不将receipt/JSON合法性冒作业务来源真实性。"""
    good, bad = [], []
    for accounts in (1, 500):
        for resources in (0, 2500000):
            row = dict(base, account_count=accounts, resource_count=resources)
            good.append((f"accounts{accounts}resources{resources}", encode(row)))
    for key, values in (
        ("account_count", (-1, 0, 501, 2**63 - 1)),
        ("resource_count", (-1, 2500001, 2**63 - 1)),
    ):
        for index, value in enumerate(values):
            bad.append((key + "Range" + str(index), encode(dict(base, **{key: value}))))
        for label, value in (
            ("String", "1"),
            ("Double", 1.0),
            ("True", True),
            ("False", False),
            ("Array", []),
            ("Object", {}),
        ):
            bad.append((key + label, encode(dict(base, **{key: value}))))
        scientific = encode(dict(base, **{key: "SCIENTIFIC_NUMBER_PLACEHOLDER"}))
        bad.append(
            (key + "Scientific", scientific.replace('"SCIENTIFIC_NUMBER_PLACEHOLDER"', "1e0"))
        )
    for key in base:
        missing = dict(base)
        del missing[key]
        # 保持6字段，让此负例准确覆盖CONTAINS_PATH而不是仅JSON_LENGTH。
        missing["unrelated_replacement_key"] = 1
        bad.append((key + "Missing", encode(missing)))
        bad.append((key + "Null", encode(dict(base, **{key: None}))))
    for label, change in (
        ("RegistryMismatch", {"registry_id": "not-the-inserted-registry"}),
        ("BindingInvalid", {"binding_sha256": "g" * 64}),
        ("BindingNumeric", {"binding_sha256": 123}),
        ("ObservedObject", {"observed_at": {}}),
        ("ExecutionTrue", {"execution_authorized": True}),
        ("ExecutionStringFalse", {"execution_authorized": "false"}),
        ("ExecutionNumericZero", {"execution_authorized": 0}),
    ):
        bad.append((label, encode(dict(base, **change))))
    return good, bad


def assert_check_diagnostics(rows, *, expected_error=None):
    # SHOW WARNINGS也包含Error3819行；只允许该精确错误，不丢弃额外warning/note。
    codes = [int(row[1]) for row in rows]
    unexpected = [code for code in codes if code != expected_error]
    if unexpected:
        raise AssertionError({"unexpected_diagnostic_codes": sorted(set(unexpected))})
    if expected_error is not None and expected_error not in codes:
        raise AssertionError({"expected_diagnostic_code": expected_error, "actual_codes": codes})


def run_meta_receipt_bounds_checks(admin, database, cases):
    guard_meta_receipt_target(admin, database)
    import pymysql

    def counts():
        try:
            result = []
            with admin.cursor() as cursor:
                for table in TABLES:
                    cursor.execute("SELECT COUNT(*) FROM " + table)
                    result.append(cursor.fetchone()[0])
            return tuple(result)
        finally:
            admin.rollback()

    before = counts()
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id,actor_id,operation,key_hash,intent_hash,registry_id,"
                "receipt_json,created_at FROM orbit_meta_raw_idempotency ORDER BY "
                "tenant_id,actor_id,operation,key_hash LIMIT 1"
            )
            existing = cursor.fetchone()
    finally:
        admin.rollback()
    if existing is None:
        raise ValueError("需要主线先执行真实045登记以提供完整回执；不自造来源")
    receipt = existing[6]
    receipt = json.loads(receipt) if isinstance(receipt, (str, bytes)) else receipt
    if not isinstance(receipt, dict) or set(receipt) != {
        "registry_id",
        "binding_sha256",
        "observed_at",
        "account_count",
        "resource_count",
        "execution_authorized",
    }:
        raise AssertionError("已有真实回执不是原6字段")
    good, bad = receipt_probes(deepcopy(receipt))
    statement = (
        "INSERT INTO orbit_meta_raw_idempotency(tenant_id,actor_id,operation,key_hash,"
        "intent_hash,registry_id,receipt_json,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)"
    )
    actual_valid, actual_invalid = 0, 0

    def insert_probe(label, encoded, expected_valid):
        identifier = str(uuid4())
        # 每个探针独占完整key/registry；只替换模板中的原ID，错绑负例不替换。
        body = encoded.replace(encode(existing[5]), encode(identifier))
        key = hashlib.sha256(uuid4().bytes).hexdigest()
        values = (*existing[:3], key, existing[4], identifier, body, existing[7])
        try:
            admin.begin()
            with admin.cursor() as cursor:
                try:
                    cursor.execute(statement, values)
                except pymysql.err.MySQLError as error:
                    actual_code = error.args[0] if error.args else None
                    if expected_valid or actual_code != 3819:
                        raise AssertionError(
                            {
                                "probe": label,
                                "actual_errno": actual_code,
                                "expected_errno": None if expected_valid else 3819,
                            }
                        ) from None
                    cursor.execute("SHOW WARNINGS")
                    assert_check_diagnostics(cursor.fetchall(), expected_error=3819)
                else:
                    cursor.execute("SHOW WARNINGS")
                    assert_check_diagnostics(cursor.fetchall())
                    if not expected_valid:
                        raise AssertionError(
                            {"probe": label, "expected_errno": 3819, "actual": "ACCEPTED"}
                        )
        finally:
            admin.rollback()
        assert counts() == before, "探针rollback后六表不得改变"

    for label, body in good:
        insert_probe(label, body, True)
        actual_valid += 1
    assert actual_valid == 4
    cases.append(META_RECEIPT_BOUNDS_CASES[0])
    for label, body in bad:
        insert_probe(label, body, False)
        actual_invalid += 1
    cases.append(META_RECEIPT_BOUNDS_CASES[1])
    try:
        admin.begin()
        with admin.cursor() as cursor:
            # 只测完整旧ledger的DB noop，不冒称此步再次调用了业务成功键重放。
            cursor.execute(
                statement + " ON DUPLICATE KEY UPDATE key_hash=key_hash",
                (*existing[:6], encode(receipt), existing[7]),
            )
            cursor.execute("SHOW WARNINGS")
            assert_check_diagnostics(cursor.fetchall())
            cursor.execute(
                "SELECT registry_id,receipt_json,created_at FROM orbit_meta_raw_idempotency "
                "WHERE tenant_id=%s AND actor_id=%s AND operation=%s AND key_hash=%s",
                existing[:4],
            )
            saved = cursor.fetchone()
            saved_receipt = saved[1]
            saved_receipt = (
                json.loads(saved_receipt)
                if isinstance(saved_receipt, (str, bytes))
                else saved_receipt
            )
            assert (saved[0], saved[2]) == (existing[5], existing[7])
            assert saved_receipt == receipt
    finally:
        admin.rollback()
    assert counts() == before
    cases.append(META_RECEIPT_BOUNDS_CASES[2])
    return {
        "valid_boundary_inserts": actual_valid,
        "invalid_receipts_rejected_3819": actual_invalid,
        "unexpected_warning_codes": [],
        "six_table_counts_unchanged": True,
        "scope": "REAL_CHECK_INSERTS_ROLLBACK_AND_LEDGER_NOOP_NOT_BUSINESS_REPLAY",
    }
