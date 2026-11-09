"""复用已隔离的数据库夹具，验证授权状态机，不进行外部OIDC网络交换。"""

import asyncio
import base64
import hashlib
import json
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

AUTHORIZATION_STORE_CASES = [
    "pythonOidcAuthorizationEncryptedPkceAndOneConcurrentClaim",
    "pythonOidcAuthorizationBindingExpiryAndProviderRevision",
    "pythonOidcAuthorizationAuditRollbackAndUnknownNeverRetries",
]


async def run_authorization_store_checks(admin, sessions, cipher, tenant, provider, binding, cases):
    from orbit_api.authorization_store import AuthorizationStore
    from orbit_api.errors import OrbitError
    from orbit_api.oidc_contract import opaque_token

    store = AuthorizationStore(cipher)

    async def start():
        async with sessions() as db, db.begin():
            return await store.start(db, tenant, provider, 1, binding, "/orbit/users", str(uuid4()))

    async def claim(attempt, bound=binding):
        async with sessions() as db, db.begin():
            return await store.claim(db, attempt.state, bound, str(uuid4()))

    async def rejected(attempt, bound=binding):
        try:
            await claim(attempt, bound)
        except OrbitError as error:
            assert error.status in {401, 409}
        else:
            raise AssertionError("授权事务不应通过认领")

    attempt = await start()
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT state_digest,binding_digest,protected_json,"
            "TIMESTAMPDIFF(SECOND,created_at,expires_at) "
            "FROM orbit_oidc_authorization WHERE id=%s",
            (attempt.id,),
        )
        digest, bound, encrypted, ttl = cursor.fetchone()
        assert len(digest) == len(bound) == 32 and ttl == 300
        assert attempt.state not in encrypted and attempt.nonce not in encrypted
        assert set(json.loads(encrypted)) == {"envelope"}
    outcomes = await asyncio.gather(claim(attempt), claim(attempt), return_exceptions=True)
    successes = [value for value in outcomes if not isinstance(value, BaseException)]
    failures = [value for value in outcomes if isinstance(value, OrbitError)]
    assert len(successes) == len(failures) == 1 and failures[0].status == 401
    claimed = successes[0]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(claimed.verifier.encode()).digest())
    assert challenge.rstrip(b"=").decode() == attempt.challenge
    assert claimed.nonce == attempt.nonce and claimed.return_to == "/orbit/users"
    await rejected(attempt)
    cases.append(AUTHORIZATION_STORE_CASES[0])

    wrong = await start()
    await rejected(wrong, opaque_token())
    assert (await claim(wrong)).id == wrong.id
    expired = await start()
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_oidc_authorization SET expires_at=UTC_TIMESTAMP(3)-INTERVAL 1 SECOND "
            "WHERE id=%s",
            (expired.id,),
        )
    await rejected(expired)
    changed = await start()
    with admin.cursor() as cursor:
        cursor.execute("UPDATE orbit_system_configuration SET revision=2 WHERE id=%s", (provider,))
    try:
        await rejected(changed)
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_system_configuration SET revision=1 WHERE id=%s", (provider,)
            )
    cases.append(AUTHORIZATION_STORE_CASES[1])

    rollback = await start()
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER auth_flow_audit_fail BEFORE INSERT ON orbit_auth_audit "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' "
            "SET MESSAGE_TEXT='fixture auth flow audit failure'"
        )
    try:
        try:
            await claim(rollback)
        except SQLAlchemyError:
            pass
        else:
            raise AssertionError("审计失败必须回滚认领")
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS auth_flow_audit_fail")
    recovered = await claim(rollback)
    async with sessions() as db, db.begin():
        await store.fail(db, recovered, "EXCHANGE_UNKNOWN", str(uuid4()))
    await rejected(rollback)
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT status,failure_code FROM orbit_oidc_authorization WHERE id=%s", (rollback.id,)
        )
        assert cursor.fetchone() == ("FAILED", "EXCHANGE_UNKNOWN")
    cases.append(AUTHORIZATION_STORE_CASES[2])
