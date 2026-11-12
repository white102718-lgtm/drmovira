"""真实 MySQL/Redis 人员认证验收；临时人员/角色/审计均在同一事务中回滚。"""

import asyncio
import base64
import json
import os
import secrets
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# 验收执行机显式指定已受控的生产配置位置；不打印配置内容。
if os.environ.get("ORBIT_CHECK_PRIVATE_ENV"):
    from pathlib import Path
    from config import orbit_runtime

    orbit_runtime.PRIVATE_ENV = Path(os.environ["ORBIT_CHECK_PRIVATE_ENV"])

from module_admin.entity.vo.login_vo import UserLogin
from module_identity.service.identity_service import (
    CredentialAuthenticationService,
    CredentialAuthenticationError,
    IdentitySecurityEventService,
)
from utils.pwd_util import PwdUtil

from orbit_api.credentials import CredentialCipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import parse_identity_write
from orbit_api.identity_guard import protect_business_identity_event
from orbit_api.role_store import RoleStore
from orbit_api.user_create_store import UserCreateStore
from orbit_api.user_update_store import UserUpdateStore
from orbit_api.user_password_store import UserPasswordStore
from orbit_api.user_credentials import parse_local_user, parse_password_reset


def raw(value):
    return json.dumps(value).encode()


async def run():
    engine = create_async_engine(os.environ["ORBIT_CHECK_DATABASE_URL"])
    redis = Redis(
        host=os.environ.get("ORBIT_PYTHON_REDIS_HOST", "127.0.0.1"),
        port=int(os.environ.get("ORBIT_PYTHON_REDIS_PORT", "6379")),
        db=int(os.environ.get("ORBIT_PYTHON_REDIS_DATABASE", "0")),
        decode_responses=True,
    )
    await redis.ping()
    tokens = DirectoryTokens(
        CredentialCipher("test", {"test": base64.b64encode(os.urandom(32)).decode()})
    )
    creates, updates, resets = (
        UserCreateStore(tokens),
        UserUpdateStore(tokens),
        UserPasswordStore(tokens),
    )
    IdentitySecurityEventService.register_business_guard(protect_business_identity_event)
    actor = int(os.environ.get("ORBIT_CHECK_ACTOR_ID", "1"))
    phone = "19" + str(secrets.randbelow(10**9)).zfill(9)
    password, new_password = secrets.token_urlsafe(18), secrets.token_urlsafe(18)
    passed = []
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        try:
            context, _ = await creates.context(session, actor)
            caps = await creates.capabilities(session, actor, "")
            csrf = caps["csrf_token"]
            role = await RoleStore(tokens).save(
                session,
                actor,
                "",
                csrf,
                str(uuid4()),
                parse_identity_write(
                    "ROLE",
                    raw(
                        {
                            "name": "人员密码回滚验收" + uuid4().hex[:8],
                            "menu_codes": ["accounts"],
                            "permission_codes": ["accounts.read"],
                        }
                    ),
                ),
                None,
                0,
                str(uuid4()),
            )
            fields = {
                "display_name": "人员回滚验收",
                "nickname": "验收",
                "email": "local-check@example.com",
                "phone": phone,
                "team_id": context.team_id,
                "role_ids": [role["id"]],
                "data_role": "USER",
                "managed_team_ids": [],
                "status": "ENABLED",
            }
            value = parse_local_user(raw(fields | {"password": password}))
            key = str(uuid4())
            person = await creates.save(session, actor, "", csrf, key, value, None, 0, str(uuid4()))
            replay = await creates.save(session, actor, "", csrf, key, value, None, 0, str(uuid4()))
            assert (
                person == replay
                and person["identity_status"] == "LOCAL_ACCOUNT"
                and person["login_account"] == phone
            )
            assert "password" not in person and password not in json.dumps(person)
            native = (
                await session.execute(
                    text(
                        "SELECT user_id FROM orbit_business_user WHERE tenant_id=:tenant AND id=:id"
                    ),
                    {"tenant": context.tenant_id, "id": person["id"]},
                )
            ).scalar_one()

            async def login(secret):
                # 调用与线上验证码通过后相同的原生认证函数；不跳过密码或停用判断。
                await session.flush()
                session.expire_all()
                return await CredentialAuthenticationService.authenticate_legacy(
                    redis,
                    session,
                    UserLogin(userName=phone, password=secret, captchaEnabled=False),
                    client_ip="127.0.0.1",
                )

            assert (await login(password))[0].user_id == native
            passed.append("direct creation/idempotency/native password login")
            try:
                await creates.save(
                    session, actor, "", csrf, str(uuid4()), value, None, 0, str(uuid4())
                )
                raise AssertionError("duplicate account accepted")
            except OrbitError as error:
                assert error.code == "LOGIN_ACCOUNT_CONFLICT"
            auth_before = (
                await session.execute(
                    text("SELECT auth_version FROM sys_identity_subject WHERE user_id=:id"),
                    {"id": native},
                )
            ).scalar_one()
            person = await updates.save(
                session,
                actor,
                "",
                csrf,
                str(uuid4()),
                parse_identity_write("USER", raw(fields | {"status": "DISABLED"})),
                person["id"],
                person["revision"],
                str(uuid4()),
            )
            try:
                await login(password)
                raise AssertionError("disabled user logged in")
            except CredentialAuthenticationError as error:
                assert error.reason == "user_disabled"
            auth_disabled = (
                await session.execute(
                    text("SELECT auth_version FROM sys_identity_subject WHERE user_id=:id"),
                    {"id": native},
                )
            ).scalar_one()
            assert auth_disabled > auth_before
            person = await updates.save(
                session,
                actor,
                "",
                csrf,
                str(uuid4()),
                parse_identity_write("USER", raw(fields)),
                person["id"],
                person["revision"],
                str(uuid4()),
            )
            assert (await login(password))[0].user_id == native
            passed.append("disable blocks native login/enable restores access/auth version revoked")
            reset_key, revision = str(uuid4()), person["revision"]
            reset_value = parse_password_reset(raw({"password": new_password}))
            person = await resets.save(
                session,
                actor,
                "",
                csrf,
                reset_key,
                reset_value,
                person["id"],
                revision,
                str(uuid4()),
            )
            auth_reset = (
                await session.execute(
                    text("SELECT auth_version FROM sys_identity_subject WHERE user_id=:id"),
                    {"id": native},
                )
            ).scalar_one()
            assert auth_reset > auth_disabled
            again = await resets.save(
                session,
                actor,
                "",
                csrf,
                reset_key,
                reset_value,
                person["id"],
                revision,
                str(uuid4()),
            )
            assert again == person
            assert (
                await session.execute(
                    text("SELECT auth_version FROM sys_identity_subject WHERE user_id=:id"),
                    {"id": native},
                )
            ).scalar_one() == auth_reset
            try:
                await login(password)
                raise AssertionError("old password accepted")
            except CredentialAuthenticationError as error:
                assert error.reason == "invalid_credentials"
            assert (await login(new_password))[0].user_id == native
            hashed = (
                await session.execute(
                    text("SELECT password FROM sys_user WHERE user_id=:id"), {"id": native}
                )
            ).scalar_one()
            assert hashed != new_password and PwdUtil.verify_password(new_password, hashed)
            persisted = (
                (
                    await session.execute(
                        text(
                            "SELECT response_json FROM orbit_directory_idempotency WHERE tenant_id=:tenant AND actor_id=:actor AND request_key IN (:create_key,:reset_key)"
                        ),
                        {
                            "tenant": context.tenant_id,
                            "actor": actor,
                            "create_key": key,
                            "reset_key": reset_key,
                        },
                    )
                )
                .scalars()
                .all()
            )
            assert all(
                password not in str(item) and new_password not in str(item) for item in persisted
            )
            passed.append(
                "reset rejects old password/accepts new/replay does not revoke twice/no plaintext persisted"
            )
            try:
                await resets.save(
                    session,
                    actor,
                    "",
                    csrf,
                    str(uuid4()),
                    reset_value,
                    person["id"],
                    revision,
                    str(uuid4()),
                )
                raise AssertionError("stale revision accepted")
            except OrbitError as error:
                assert error.code == "REVISION_CONFLICT"
            passed.append("stale reset rejected")
        finally:
            await session.rollback()
            await redis.delete("password_error_count:" + phone)
            await redis.aclose()
    async with engine.connect() as connection:
        assert not (
            await connection.execute(
                text("SELECT user_id FROM sys_user WHERE user_name=:name"), {"name": phone}
            )
        ).first()
    await engine.dispose()
    print(
        json.dumps({"passed": passed, "all_database_writes_rolled_back": True}, ensure_ascii=False)
    )


if __name__ == "__main__":
    asyncio.run(run())
