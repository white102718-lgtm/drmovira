"""设备导航不隐式授予读写，四项精确动作只编译原授权。"""

import pytest

from orbit_api.role_bridge import BUSINESS_MENUS, compiled_menu_ids


@pytest.mark.parametrize(
    "action,leaf", [("read", 31061), ("enroll", 31062), ("revoke", 31063), ("probe", 31064)]
)
def test_environment_navigation_and_actions_are_independent(action, leaf):
    assert BUSINESS_MENUS["environments"][0:2] == (31060, "")
    assert compiled_menu_ids(["environments"], ["environments." + action]) == [31000, 31060, leaf]
    assert compiled_menu_ids([], ["environments." + action]) == [leaf]


def test_environment_navigation_alone_grants_no_action():
    assert compiled_menu_ids(["environments"], []) == [31000, 31060]
