"""规则页面导航独立于原六动作，不借菜单附送读取权限。"""

from pathlib import Path

import pytest

from orbit_api.role_bridge import BUSINESS_MENUS, compiled_menu_ids


@pytest.mark.parametrize(
    ("actions", "action_ids"),
    [
        ([], []),
        (["rules.read"], [31041]),
        (["rules.create"], [31042]),
        (["rules.edit"], [31043]),
        (["rules.enable"], [31044]),
        (["rules.pause"], [31045]),
        (["rules.archive"], [31046]),
    ],
)
def test_menu_never_adds_ungranted_actions(actions, action_ids):
    assert compiled_menu_ids(["rules"], actions) == sorted([31000, 31040, 31047, *action_ids])


def test_action_alone_never_grants_menu():
    assert compiled_menu_ids([], ["rules.create", "rules.edit"]) == [31042, 31043]
    assert BUSINESS_MENUS["rules"][1] == ""
    assert BUSINESS_MENUS["rules"][2]["rules.read"] == 31041


def test_navigation_migration_preserves_native_and_action_menus():
    migration = (
        Path(__file__).resolve().parents[1] / "orbit_api/migrations/062_rules_page_menu.sql"
    ).read_text(encoding="utf-8")
    assert "visible='0',perms=''" in migration
    assert "'orbit/rules/index'" in migration
    assert "m.menu_code='rules'" in migration
    assert "DELETE " not in migration.upper()
    assert "DROP " not in migration.upper()
