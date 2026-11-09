"""旧023领域/新原GET工具边界；只验证防误用，不把静态护栏计为真实SQL。"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "account_identities_checks", ROOT / "tools/account_identities_checks.py"
)
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


class Cursor:
    def __init__(self, database, count):
        self.database, self.count = database, count
        self.statement = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement, params=None):
        self.statement = statement
        if "information_schema" in statement:
            assert params == (self.database,)
            assert "orbit_identity_publication_provenance" in statement
            assert "orbit_identity_capability_release" in statement
            assert "orbit_identity_publication_ledger" in statement

    def fetchone(self):
        return (self.database,) if "DATABASE()" in self.statement else (self.count,)


@pytest.mark.parametrize("count", [0, 1, 2])
def test_missing_053_is_explicit_rejection_not_bare_http_compatibility(count):
    database = "orbit_py_it_" + "a" * 32
    admin = SimpleNamespace(cursor=lambda: Cursor(database, count))
    with pytest.raises(ValueError, match="053"):
        tool.require_publication_schema(admin, database)


def test_exact_uuid_schema_required_and_full_053_accepted():
    database = "orbit_py_it_" + "a" * 32
    admin = SimpleNamespace(cursor=lambda: Cursor(database, 3))
    tool.require_publication_schema(admin, database)
    with pytest.raises(ValueError):
        tool.require_publication_schema(admin, "orbit_py_it_" + "b" * 32)


def test_case_plan_preserves_original_nine_and_adds_explicit_bare_head_refusal():
    assert len(tool.CASES) == 10 and len(set(tool.CASES)) == 10
    assert (
        tool.CASES[-1] == "pythonAccountIdentitiesBareLegacyHeadCannotBypassPublicationProvenance"
    )
    for name in (
        "pythonAccountIdentitiesRegistryRevocationFailsClosed",
        "pythonAccountIdentitiesKnownCredentialExpiryFailsClosed",
        "pythonAccountIdentitiesPayloadReplacementAndLateObservationRejected",
        "pythonAccountIdentitiesAuditFailureRollsBackHeadHistoryResourcesAndEvents",
        "pythonAccountIdentitiesOnlyCompleteObservedEmptyResourcesCanSucceed",
    ):
        assert name in tool.CASES


def test_original_runner_signature_stays_compatible():
    import inspect

    assert list(inspect.signature(tool.run_account_identities_checks).parameters) == [
        "client",
        "admin",
        "headers",
        "actor_id",
        "owner_user_id",
        "owner_team_id",
        "database",
        "cases",
        "cipher",
        "denied_headers",
    ]


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("external.example", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit_preview"),
    ],
)
def test_wrong_target_is_rejected_before_sql(host, port, database):
    admin = SimpleNamespace(host=host, port=port)
    with pytest.raises(ValueError):
        tool.run_account_identities_checks(
            None, admin, None, 1, None, None, database, [], None, None
        )
