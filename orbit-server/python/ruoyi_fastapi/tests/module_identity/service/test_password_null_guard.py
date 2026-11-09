"""无本地密码的OIDC账号不能因占位哈希匹配而获得密码登录。"""

from unittest.mock import patch

import pytest

from module_identity.service.identity_service import CredentialAuthenticationService


@pytest.mark.parametrize('stored', [None, ''])
def test_missing_hash_still_checks_dummy_but_never_authenticates(stored: str | None) -> None:
    with patch('module_identity.service.identity_service.PwdUtil.verify_password', return_value=True) as verify:
        assert CredentialAuthenticationService._verify('fixture', stored) is False
        verify.assert_called_once()
        assert verify.call_args.args[1]


def test_real_hash_match_and_mismatch_are_preserved() -> None:
    for matched in (True, False):
        with patch('module_identity.service.identity_service.PwdUtil.verify_password', return_value=matched):
            assert CredentialAuthenticationService._verify('fixture', 'real-fixture-hash') is matched
