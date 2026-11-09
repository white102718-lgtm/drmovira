"""指标目录沿用monitor读取，不给目录读者附带发行或执行权限。"""

from orbit_api.role_bridge import BUSINESS_MENUS, compiled_menu_ids


def test_monitor_reader_has_original_menu_action_and_real_directory_page():
    assert compiled_menu_ids(["monitor"], ["monitor.read"]) == [31000, 31030, 31031, 310301, 310302]
    assert BUSINESS_MENUS["monitor"] == (31030, "monitor.read", {"monitor.read": 31031})


def test_monitor_action_without_menu_does_not_compile_directory_navigation():
    assert compiled_menu_ids([], ["monitor.read"]) == [31031]


def test_monitor_menu_without_read_does_not_grant_action_or_child_page():
    assert compiled_menu_ids(["monitor"], []) == [31000, 31030]
