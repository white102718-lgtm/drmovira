"""模板属于投放菜单，但读取/执行/发布动作不得由模板读取隐式获得。"""

from orbit_api.role_bridge import BUSINESS_MENUS, compiled_menu_ids


def test_template_only_role_keeps_menu_without_granting_plan_read_or_execute():
    assert compiled_menu_ids(["launch"], ["templates.read"]) == [31000, 31020, 310201]


def test_template_action_without_menu_never_creates_root_or_parent_grant():
    assert compiled_menu_ids([], ["templates.read"]) == [310201]


def test_launch_actions_and_template_actions_have_distinct_stable_numbers():
    parent, read_action, actions = BUSINESS_MENUS["launch"]
    assert parent == 31020 and read_action == "launch.read"
    assert len(actions) == len(set(actions.values())) == 11
    assert actions["launch.execute"] == 31024
    assert actions["launch.publish"] == 31025
    assert actions["templates.archive"] == 310205
    assert actions["tasks.read"] == 310206


def test_task_only_role_keeps_menu_without_granting_plan_read():
    """任务观察者可进入投放菜单，但不获得计划读取动作。"""
    assert compiled_menu_ids(["launch"], ["tasks.read"]) == [31000, 31020, 310206]
