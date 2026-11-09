"""任务快照口径：不绑定无关目录修订，确实绑定发起人/数据角色/团队及素材内容。"""

from dataclasses import replace

import pytest

from orbit_api.authorization import BusinessContext
from orbit_api.material_job_policy import material_job_scope


@pytest.fixture
def context():
    return BusinessContext(1, "tenant", "USER", "person", "team")


@pytest.fixture
def asset():
    return {
        "id": "asset",
        "owner_user_id": "person",
        "owner_team_id": "team",
        "sha256": "a" * 64,
        "mime": "image/png",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor_id", 2),
        ("tenant_id", "other"),
        ("subject_id", "another"),
        ("team_id", "new-team"),
        ("data_role", "TEAM_ADMIN"),
    ],
)
def test_relevant_identity_changes_invalidate(context, asset, field, value):
    assert material_job_scope(context, asset) != material_job_scope(
        replace(context, **{field: value}), asset
    )


@pytest.mark.parametrize("field", ["id", "owner_user_id", "owner_team_id", "sha256", "mime"])
def test_relevant_material_changes_invalidate(context, asset, field):
    assert material_job_scope(context, asset) != material_job_scope(
        context, asset | {field: "changed"}
    )


def test_unrelated_display_revision_or_directory_clock_is_not_a_scope_dependency(context, asset):
    assert material_job_scope(context, asset) == material_job_scope(
        context, asset | {"name": "新名称", "revision": 100, "unrelated_directory_clock": 99}
    )
