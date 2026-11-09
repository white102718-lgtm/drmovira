"""标签动作独立授权，菜单导航不隐式授予素材读取。"""

import pytest

from orbit_api.role_bridge import BUSINESS_MENUS, compiled_menu_ids


@pytest.mark.parametrize(
    "action,leaf", [("read", 31055), ("create", 31056), ("edit", 31057), ("archive", 31058)]
)
def test_taxonomy_action_menu_does_not_grant_assets_read(action, leaf):
    assert BUSINESS_MENUS["assets"][1] == ""
    assert compiled_menu_ids(["assets"], ["tags." + action]) == [31000, 31050, leaf]
    assert BUSINESS_MENUS["assets"][2]["assets.read"] == 31051
