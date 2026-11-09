"""实际密钥派生验证三类环境游标注册且用途隔离。"""

import base64
import secrets

import pytest

from orbit_api.credentials import CredentialCipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError


def test_environment_cursor_signatures_are_registered_and_isolated():
    tokens = DirectoryTokens(
        CredentialCipher("test", {"test": base64.b64encode(secrets.token_bytes(32)).decode()})
    )
    for purpose, other in [
        ("EXECUTION_AGENT_CURSOR_V1", "PROFILE_BINDING_CURSOR_V1"),
        ("PROFILE_BINDING_CURSOR_V1", "EXECUTION_AGENT_CURSOR_V1"),
        ("AGENT_PROFILE_CURSOR_V1", "EXECUTION_AGENT_CURSOR_V1"),
        ("EXECUTION_AGENT_CURSOR_V1", "AGENT_PROFILE_CURSOR_V1"),
        ("AGENT_PROFILE_CURSOR_V1", "PROFILE_BINDING_CURSOR_V1"),
    ]:
        token = tokens.issue(purpose, {"binding": "isolated"})
        assert tokens.verify(purpose, token)["binding"] == "isolated"
        with pytest.raises(OrbitError):
            tokens.verify(other, token)
