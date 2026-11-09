"""独立纯DAG结构/oracle，不注册Task，不把本地fixture当生产能力证明。"""

import copy
from dataclasses import replace
from uuid import UUID

import pytest

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_allocation import (
    build_compatibility_evidence,
    solve_allocation,
)
from orbit_api.launch_contract import MAX_CONFIG_BYTES
from orbit_api.launch_dag import build_launch_dag
from orbit_api.launch_expansion import ad_slots


def uid(n):
    return str(UUID(int=n))


def plan(*, accounts=1, copies=1, activate=False, assets=1):
    return {
        "name": "独立纯图夹具",
        "ownership": {"owner_user_id": uid(900001), "owner_team_id": uid(900002)},
        "account_ids": [uid(900010 + n) for n in range(accounts)],
        "campaigns": [
            {
                "local_id": uid(1),
                "copies": 1,
                "adsets": [
                    {
                        "local_id": uid(2),
                        "copies": 1,
                        "ads": [{"local_id": uid(3), "copies": copies}],
                    }
                ],
            }
        ],
        "asset_ids": [uid(800000 + n) for n in range(assets)],
        "identity_bindings": [],
        "allow_repeat": True,
        "activate_after_create": activate,
        "execution_mode": "META_API",
    }


def fixture(value, *, evaluator=lambda _slot, _asset: True):
    slots = ad_slots(value)
    revisions = {asset: 3 for asset in value["asset_ids"]}
    evidence = build_compatibility_evidence(
        slots,
        value["asset_ids"],
        capability_version="isolated-fixture-only",
        source_hash="a" * 64,
        verified=True,
        complete=True,
        evaluate=evaluator,
        material_revisions=revisions,
    )
    result = solve_allocation(
        slots,
        value["asset_ids"],
        evidence,
        allow_repeat=value["allow_repeat"],
        seed=0,
        material_revisions=revisions,
    )
    return dict(
        plan_revision=1, allocation=result, compatibility=evidence, material_revisions=revisions
    )


def build(value, **changes):
    args = fixture(value)
    args.update(changes)
    return build_launch_dag(value, **args)


def ancestors(nodes):
    """小图独立集合oracle；大图采用线性gate归纳，不构造二次方闭包。"""
    output = {}
    for node in nodes:
        assert node.node_key not in output
        assert len(node.node_key) <= 512
        assert len(node.parent_keys) <= 100
        assert all(parent in output for parent in node.parent_keys)
        output[node.node_key] = set(node.parent_keys)
        for parent in node.parent_keys:
            output[node.node_key].update(output[parent])
    return output


def test_single_ad_real_operations_and_complete_count_no_task_authorization():
    result = build(plan())
    assert dict(result.kind_counts) == {
        "UPLOAD": 1,
        "CAMPAIGN": 1,
        "ADSET": 1,
        "CREATIVE": 1,
        "AD": 1,
        "VERIFY": 5,
    }
    assert result.total_dag_node_count == 10 == len(result.nodes)
    assert (result.campaign_count, result.adset_count, result.ad_count) == (1, 1, 1)
    assert result.execution_authorized is False
    assert not hasattr(result, "task_id")
    graph = ancestors(result.nodes)
    ad = next(row for row in result.nodes if row.kind == "AD")
    assert {"UPLOAD", "CAMPAIGN", "ADSET", "CREATIVE"}.issubset(
        {row.kind for row in result.nodes if row.node_key in graph[ad.node_key]}
    )


def test_upload_reused_only_inside_same_account_creatives_never_reused():
    result = build(plan(accounts=2, copies=3))
    kinds = dict(result.kind_counts)
    assert kinds["UPLOAD"] == 2
    assert kinds["CREATIVE"] == kinds["AD"] == 6
    uploads = [row for row in result.nodes if row.kind == "UPLOAD"]
    assert len({row.account_id for row in uploads}) == 2
    assert all(row.asset_revision == 3 for row in uploads)


def test_unused_pool_member_not_uploaded_or_counted_as_executed_operation():
    value = plan(copies=2, assets=2)
    args = fixture(value, evaluator=lambda _slot, asset: asset == value["asset_ids"][0])
    result = build_launch_dag(value, **args)
    uploads = [row for row in result.nodes if row.kind == "UPLOAD"]
    assert len(uploads) == 1
    assert uploads[0].asset_id == value["asset_ids"][0]


def test_all_actual_copies_and_sibling_branches_expand_without_cross_cartesian():
    value = plan(copies=2)
    value["campaigns"][0]["copies"] = 3
    value["campaigns"][0]["adsets"][0]["copies"] = 4
    value["campaigns"].append(
        {
            "local_id": uid(11),
            "copies": 2,
            "adsets": [
                {"local_id": uid(12), "copies": 1, "ads": [{"local_id": uid(13), "copies": 3}]}
            ],
        }
    )
    result = build(value)
    assert (result.campaign_count, result.adset_count, result.ad_count) == (5, 14, 30)
    assert result.total_dag_node_count == 2 + 2 * 5 + 2 * 14 + 4 * 30


def test_activation_all_config_verified_before_every_enable_parent_enable_verified():
    result = build(plan(accounts=2, copies=3, activate=True))
    graph = ancestors(result.nodes)
    original_ad_reads = {
        row.node_key
        for row in result.nodes
        if row.kind == "VERIFY" and row.purpose == "CREATE" and row.target_key.startswith("AD/")
    }
    enables = [row for row in result.nodes if row.kind == "ENABLE"]
    assert len(enables) == 2 + 2 + 6
    assert all(original_ad_reads <= graph[row.node_key] for row in enables)
    assert result.total_dag_node_count == 2 * 2 + 4 * 2 + 4 * 2 + 6 * 6
    assert not any(row.purpose == "ACTIVATION_READ" for row in result.nodes)
    for row in result.nodes:
        if row.purpose == "ENABLE" and row.kind == "VERIFY":
            assert row.target_key in {item.target_key for item in enables}


@pytest.mark.parametrize("count", [1, 98, 99, 100, 197, 198, 199, 500])
def test_activation_gate_group_boundaries_no_fake_barrier_no_truncated_parents(count):
    value = plan(activate=True)
    value["campaigns"][0]["adsets"][0]["ads"] = [
        {"local_id": uid(1000 + n), "copies": 1} for n in range(count)
    ]
    result = build(value)
    original_reads = [
        row
        for row in result.nodes
        if row.kind == "VERIFY" and row.purpose == "CREATE" and row.target_key.startswith("AD/")
    ]
    # 稳定顺序累计coverage，仅组尾有前组依赖。oracle不依赖生产组大小常量。
    coverage = {}
    for row in result.nodes:
        own = {row.node_key} if row in original_reads else set()
        coverage[row.node_key] = own.union(*(coverage[p] for p in row.parent_keys))
        assert len(row.parent_keys) <= 100
    all_reads = {row.node_key for row in original_reads}
    assert len(all_reads) == count
    assert all(coverage[row.node_key] == all_reads for row in result.nodes if row.kind == "ENABLE")
    assert dict(result.kind_counts)["VERIFY"] == 1 + 1 + 1 + 2 * count + 2 + count
    assert all(
        row.target_key in {n.node_key for n in result.nodes}
        for row in result.nodes
        if row.kind == "VERIFY"
    )


def test_stable_graph_nonmutating_binds_revision_full_config_and_amount_strings():
    value = plan(copies=2)
    value["campaigns"][0]["budget"] = {
        "owner": "CAMPAIGN",
        "type": "DAILY",
        "amount": "0.100000",
        "currency": "USD",
        "spend_cap": None,
    }
    before = copy.deepcopy(value)
    first = build(value)
    assert value == before
    assert first == build(value)
    assert first.budget_totals == (("USD", "0.100000"),)
    assert first.graph_hash != build(value, plan_revision=2).graph_hash
    value["campaigns"][0]["adsets"][0]["ads"][0]["title"] = "不同内容"
    second = build(value)
    assert [row.node_key for row in first.nodes] == [row.node_key for row in second.nodes]
    assert first.graph_hash != second.graph_hash
    assert first.nodes[0].configuration_hash != second.nodes[0].configuration_hash


def test_original_array_pointers_preserved_despite_uuid_topological_sort():
    value = plan()
    value["campaigns"].insert(
        0,
        {
            "local_id": uid(100),
            "copies": 1,
            "adsets": [
                {"local_id": uid(101), "copies": 1, "ads": [{"local_id": uid(102), "copies": 1}]}
            ],
        },
    )
    result = build(value)
    campaigns = [row for row in result.nodes if row.kind == "CAMPAIGN"]
    assert [row.source_pointer for row in campaigns] == ["/campaigns/1", "/campaigns/0"]


def test_upload_and_campaign_are_independent_but_creative_requires_both_real_reads():
    result = build(plan())
    graph = ancestors(result.nodes)
    campaign = next(row for row in result.nodes if row.kind == "CAMPAIGN")
    creative = next(row for row in result.nodes if row.kind == "CREATIVE")
    assert campaign.parent_keys == ()
    assert len(creative.parent_keys) == 2
    assert {row.kind for row in result.nodes if row.node_key in graph[creative.node_key]} >= {
        "UPLOAD",
        "CAMPAIGN",
        "ADSET",
        "VERIFY",
    }


def test_allocation_revision_changes_node_configuration_hash_not_only_graph_hash():
    value = plan()
    first_args = fixture(value)
    first = build_launch_dag(value, **first_args)
    second_args = fixture(value)
    second_args["allocation"] = solve_allocation(
        ad_slots(value),
        value["asset_ids"],
        second_args["compatibility"],
        allow_repeat=True,
        seed=1,
        material_revisions=second_args["material_revisions"],
    )
    second = build_launch_dag(value, **second_args)
    assert first.nodes[0].configuration_hash != second.nodes[0].configuration_hash
    assert first.graph_hash != second.graph_hash


def test_incompatible_assignment_rejected_even_if_usage_and_original_hash_look_valid():
    value = plan(copies=2, assets=2)
    assets = value["asset_ids"]
    args = fixture(value, evaluator=lambda slot, asset: asset == assets[slot.ad_copy - 1])
    original = args["allocation"]
    args["allocation"] = replace(
        original,
        assignments=(
            (original.assignments[0][0], assets[1]),
            (original.assignments[1][0], assets[0]),
        ),
    )
    with pytest.raises(OrbitError) as info:
        build_launch_dag(value, **args)
    assert info.value.status == 422
    assert info.value.pointer == "/allocation_id"


def test_unverified_or_incomplete_provider_reports_dependency_not_business_success():
    value = plan()
    for field in ("verified", "complete"):
        args = fixture(value)
        args["compatibility"] = replace(args["compatibility"], **{field: False})
        with pytest.raises(OrbitError) as info:
            build_launch_dag(value, **args)
        assert info.value.status == 503
        assert info.value.code == "CAPABILITY_COMPATIBILITY_UNAVAILABLE"


def test_uuid_set_order_stable_keys_but_original_plan_semantics_remain_hashed():
    value = plan(accounts=2, assets=2)
    first = build(value)
    value["account_ids"].reverse()
    value["asset_ids"].reverse()
    second = build(value)
    assert [n.node_key for n in first.nodes] == [n.node_key for n in second.nodes]
    # DAG指纹将UUID集合规范排序，保留真正配置数组的语义顺序。
    assert first.plan_input_hash == second.plan_input_hash
    assert first.graph_hash == second.graph_hash


@pytest.mark.parametrize("path", ["accounts", "campaigns", "groups", "ads"])
def test_incomplete_draft_rejected_with_exact_local_pointer(path):
    value = plan()
    expected = "/account_ids"
    if path == "accounts":
        value["account_ids"] = []
    elif path == "campaigns":
        value["campaigns"] = []
        expected = "/campaigns"
    elif path == "groups":
        value["campaigns"][0]["adsets"] = []
        expected = "/campaigns/0/adsets"
    else:
        value["campaigns"][0]["adsets"][0]["ads"] = []
        expected = "/campaigns/0/adsets/0/ads"
    with pytest.raises(OrbitError) as info:
        build_launch_dag(
            value, plan_revision=1, allocation=None, compatibility=None, material_revisions={}
        )
    assert info.value.status == 422
    assert info.value.pointer == expected


@pytest.mark.parametrize("revision", [True, 0, -1, 9007199254740992])
def test_revision_invalid(revision):
    with pytest.raises(OrbitError) as info:
        build(plan(), plan_revision=revision)
    assert info.value.pointer == "/revision"


def test_missing_trusted_provider_never_returns_zero_graph_or_fake_valid():
    value = plan()
    args = fixture(value)
    args["compatibility"] = None
    with pytest.raises(OrbitError) as info:
        build_launch_dag(value, **args)
    assert info.value.status == 503
    args["allocation"] = None
    with pytest.raises(OrbitError) as info:
        build_launch_dag(value, **args)
    assert info.value.code == "ALLOCATION_UNAVAILABLE"


@pytest.mark.parametrize(
    "mutation", ["partial", "duplicate", "foreign", "usage", "hash", "version", "material"]
)
def test_partial_wrong_or_stale_allocation_cannot_produce_manifest(mutation):
    value = plan(copies=2)
    args = fixture(value)
    result = args["allocation"]
    if mutation == "partial":
        args["allocation"] = replace(result, assignments=result.assignments[:1])
    elif mutation == "duplicate":
        args["allocation"] = replace(result, assignments=(result.assignments[0],) * 2)
    elif mutation == "foreign":
        args["allocation"] = replace(
            result, assignments=((result.assignments[0][0], uid(999999)), result.assignments[1])
        )
    elif mutation == "usage":
        args["allocation"] = replace(result, squared_usage=0)
    elif mutation == "hash":
        args["allocation"] = replace(result, input_hash="f" * 64)
    elif mutation == "version":
        args["allocation"] = replace(result, capability_version="unknown")
    else:
        args["material_revisions"] = {value["asset_ids"][0]: 4}
    with pytest.raises(OrbitError) as info:
        build_launch_dag(value, **args)
    assert info.value.status in (409, 422)


def many_branches(count, assets):
    value = plan(activate=True, assets=assets)
    value["campaigns"] = [
        {
            "local_id": uid(1 + 3 * n),
            "copies": 1,
            "adsets": [
                {
                    "local_id": uid(2 + 3 * n),
                    "copies": 1,
                    "ads": [{"local_id": uid(3 + 3 * n), "copies": 1}],
                }
            ],
        }
        for n in range(count)
    ]
    return value


def test_exact_100000_nodes_and_100001_plus_are_counted_before_task_creation():
    # 每个系列/组/广告分支激活共14节点，6实际上传及回读=12。
    value = many_branches(7142, 6)
    result = build(value)
    assert result.total_dag_node_count == 100000
    assert len(result.nodes) == 100000
    assert max(len(row.parent_keys) for row in result.nodes) == 100
    # 再增加一条分支，原每层均远低于10000，仍必须被总DAG上限拒绝。
    value = many_branches(7143, 6)
    with pytest.raises(OrbitError) as info:
        build(value)
    assert info.value.status == 422
    assert info.value.code == "PLAN_NODE_LIMIT"


def test_exact_five_mib_canonical_plan_builds_full_dag_but_one_extra_byte_rejected():
    value = plan()
    value["channel_id"] = None
    ads = [{"local_id": uid(1000 + index), "copies": 1, "body": "x"} for index in range(5000)]
    value["campaigns"][0]["adsets"][0]["ads"] = ads
    remaining = MAX_CONFIG_BYTES - len(canonical(value).encode())
    per_ad, extra = divmod(remaining, len(ads))
    assert per_ad + 2 <= 2000
    for index, ad in enumerate(ads):
        ad["body"] += "x" * (per_ad + (index < extra))
    assert len(canonical(value).encode()) == MAX_CONFIG_BYTES
    result = build(value)
    assert result.ad_count == 5000
    assert result.total_dag_node_count == 20006
    assert len(result.nodes) == 20006
    value["name"] += "x"
    assert len(canonical(value).encode()) == MAX_CONFIG_BYTES + 1
    with pytest.raises(OrbitError) as info:
        build(value)
    assert info.value.status == 413
    assert info.value.code == "PAYLOAD_TOO_LARGE"
