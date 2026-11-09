"""用独立穷举oracle核全局最优与可行性；不作为真实能力源/SQL/平台验收。"""

from dataclasses import replace
from itertools import product
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.launch_allocation import (
    AllocationTimeout,
    Budget,
    CompatibilityEvidence,
    build_compatibility_evidence,
    solve_allocation,
    stable_assets,
)
from orbit_api.launch_expansion import Slot


def uid(index):
    return str(UUID(int=index))


def setup(masks, count):
    slots = tuple(
        Slot(uid(1), uid(2), 1, uid(3), 1, uid(4), index + 1) for index in range(len(masks))
    )
    assets = tuple(uid(100 + index) for index in range(count))
    evidence = CompatibilityEvidence(
        "verified-local-fixture-v1",
        "a" * 64,
        tuple(row.key for row in slots),
        assets,
        tuple(masks),
        ((1 << count) - 1,) * len(slots),
        True,
        True,
        digest([row.__dict__ for row in slots]),
        tuple((asset, 1) for asset in assets),
    )
    return slots, assets, evidence


def solve(masks, count, repeat=True, seed=0, **changes):
    slots, assets, evidence = setup(masks, count)
    return solve_allocation(
        slots,
        assets,
        evidence,
        allow_repeat=repeat,
        seed=seed,
        material_revisions={asset: 1 for asset in assets},
        **changes,
    )


def optimum(masks, count, repeat):
    answer = None
    for choices in product(range(count), repeat=len(masks)):
        if any(not mask & (1 << choice) for mask, choice in zip(masks, choices, strict=True)):
            continue
        usage = [choices.count(index) for index in range(count)]
        if not repeat and max(usage) > 1:
            continue
        cost = sum(value * value for value in usage)
        answer = cost if answer is None else min(answer, cost)
    return answer


def test_nonrepeat_reassigns_previous_match_instead_of_failing_greedy_trap():
    _, assets, _ = setup([3, 3], 2)
    preferred = stable_assets(assets, 0)[0]
    result = solve([3, 1 << preferred], 2, repeat=False)
    assert result.assignments[1][1] == assets[preferred]
    assert result.assignments[0][1] != assets[preferred]
    assert result.squared_usage == 2


def test_repeat_global_cost_can_reassign_old_slot_to_avoid_myopic_greedy_cost_four():
    _, assets, _ = setup([3, 3], 2)
    preferred = stable_assets(assets, 0)[0]
    result = solve([3, 1 << preferred], 2)
    assert result.squared_usage == 2
    assert {count for _, count in result.usage} == {1}


def test_all_512_three_by_three_graphs_match_independent_injective_oracle():
    for masks in product(range(8), repeat=3):
        expected = optimum(masks, 3, False)
        if expected is None:
            with pytest.raises(OrbitError) as failure:
                solve(masks, 3, repeat=False)
            assert failure.value.code == "ALLOCATION_NO_MATCH"
        else:
            result = solve(masks, 3, repeat=False)
            assert result.squared_usage == expected
            assert (
                len(result.assignments) == 3
                and len({asset for _, asset in result.assignments}) == 3
            )


def test_all_2401_nonempty_four_by_three_graphs_match_bruteforce_global_convex_optimum():
    for masks in product(range(1, 8), repeat=4):
        result = solve(masks, 3)
        assert result.squared_usage == optimum(masks, 3, True), masks
        for index, (_, asset) in enumerate(result.assignments):
            assert masks[index] & (1 << (int(UUID(asset)) - 100))


def test_same_seed_and_set_permutation_replay_identical_results_but_seed_breaks_only_ties():
    slots, assets, evidence = setup([3] * 4, 2)
    ordinary = solve([3] * 4, 2, seed=4)
    permuted = solve_allocation(
        tuple(reversed(slots)),
        tuple(reversed(assets)),
        evidence,
        allow_repeat=True,
        seed=4,
        material_revisions={asset: 1 for asset in reversed(assets)},
    )
    assert ordinary == permuted
    outcomes = {solve([3] * 4, 2, seed=seed).assignments for seed in range(16)}
    assert len(outcomes) > 1
    assert {solve([3] * 4, 2, seed=seed).squared_usage for seed in range(16)} == {8}


def test_unavoidable_usage_gap_is_valid_full_optimum_with_honest_warning():
    result = solve([1, 1, 1, 3], 2)
    assert result.squared_usage == 10
    assert sorted(count for _, count in result.usage) == [1, 3]
    assert result.warnings and len(result.assignments) == 4


@pytest.mark.parametrize(
    "changes",
    [
        {"verified": False},
        {"complete": False},
        {"capability_version": ""},
        {"source_hash": "unknown"},
        {"evaluated_masks": (1, 3)},
        {"compatible_masks": (7, 3)},
        {"compatible_masks": (True, 3)},
        {"slot_keys": ("wrong", "graph")},
        {"asset_ids": (uid(100), uid(999))},
    ],
)
def test_missing_unknown_or_mismatched_graph_is_dependency_failure_not_guessed_compatible(changes):
    slots, assets, evidence = setup([3, 3], 2)
    with pytest.raises(OrbitError) as failure:
        solve_allocation(
            slots,
            assets,
            replace(evidence, **changes),
            allow_repeat=True,
            seed=0,
            material_revisions={asset: 1 for asset in assets},
        )
    assert failure.value.status == 503


def test_known_all_incompatible_edges_are_real_no_match_not_unknown_capability():
    with pytest.raises(OrbitError) as failure:
        solve([0, 3], 2)
    assert failure.value.code == "ALLOCATION_NO_MATCH" and failure.value.status == 422


def test_builder_evaluates_full_graph_and_rejects_one_unknown_edge():
    slots, assets, _ = setup([3, 3], 2)
    calls = []

    def evaluate(slot, asset):
        calls.append((slot.key, asset))
        return asset == assets[0]

    evidence = build_compatibility_evidence(
        slots,
        assets,
        capability_version="registry-v1",
        source_hash="a" * 64,
        verified=True,
        complete=True,
        evaluate=evaluate,
        material_revisions={asset: 1 for asset in assets},
    )
    assert len(calls) == 4 and evidence.compatible_masks == (1, 1)
    with pytest.raises(OrbitError) as failure:
        build_compatibility_evidence(
            slots,
            assets,
            capability_version="registry-v1",
            source_hash="a" * 64,
            verified=True,
            complete=True,
            evaluate=lambda slot, asset: None if asset == assets[-1] else True,
            material_revisions={asset: 1 for asset in assets},
        )
    assert failure.value.status == 503


@pytest.mark.parametrize(
    "revisions", [None, {}, {uid(100): True, uid(101): 1}, {uid(100): 0, uid(101): 1}]
)
def test_every_material_revision_must_be_real_safe_integer(revisions):
    slots, assets, evidence = setup([3, 3], 2)
    with pytest.raises(OrbitError) as failure:
        solve_allocation(
            slots, assets, evidence, allow_repeat=True, seed=0, material_revisions=revisions
        )
    assert failure.value.code == "MATERIAL_VERSION_REQUIRED"


def test_timeout_is_typed_and_never_exposes_partial_assignments_or_fake_task():
    ticks = iter([0, 61])
    with pytest.raises(AllocationTimeout) as failure:
        solve([3, 3], 2, clock=lambda: next(ticks))
    assert len(failure.value.input_hash) == 64
    assert failure.value.phase == "RESIDUAL_FLOW"
    assert not hasattr(failure.value, "assignments") and not hasattr(failure.value, "task_id")


@pytest.mark.parametrize("asset_count", [2, 500])
def test_ten_thousand_slots_remain_complete_and_globally_balanced_for_verified_all_edges(
    asset_count,
):
    result = solve([(1 << asset_count) - 1] * 10000, asset_count)
    assert len(result.assignments) == 10000
    assert [count for _, count in result.usage] == [10000 // asset_count] * asset_count
    assert result.squared_usage == asset_count * (10000 // asset_count) ** 2


def test_graph_build_and_solver_share_one_deadline_instead_of_resetting_another_sixty_seconds():
    now = [0]

    def clock():
        return now[0]

    budget = Budget(60, clock, "COMPATIBILITY_GRAPH", "a" * 64)
    slots, assets, _ = setup([3, 3], 2)
    evidence = build_compatibility_evidence(
        slots,
        assets,
        capability_version="registry-v1",
        source_hash="a" * 64,
        verified=True,
        complete=True,
        evaluate=lambda *_: True,
        material_revisions={asset: 1 for asset in assets},
        work_budget=budget,
    )
    now[0] = 61
    with pytest.raises(AllocationTimeout) as failure:
        solve_allocation(
            slots,
            assets,
            evidence,
            allow_repeat=True,
            seed=0,
            material_revisions={asset: 1 for asset in assets},
            work_budget=budget,
        )
    assert budget.deadline == 60
    assert failure.value.phase == "RESIDUAL_FLOW"


def test_same_input_hash_changes_when_material_version_or_compatibility_version_changes():
    slots, assets, evidence = setup([3, 3], 2)
    original = solve([3, 3], 2)
    with pytest.raises(OrbitError) as failure:
        solve_allocation(
            slots,
            assets,
            evidence,
            allow_repeat=True,
            seed=0,
            material_revisions={assets[0]: 2, assets[1]: 1},
        )
    assert failure.value.code == "MATERIAL_VERSION_CONFLICT"
    newer = solve_allocation(
        slots,
        assets,
        replace(evidence, material_revisions=((assets[0], 2), (assets[1], 1))),
        allow_repeat=True,
        seed=0,
        material_revisions={assets[0]: 2, assets[1]: 1},
    )
    assert newer.input_hash != original.input_hash
    newest = solve_allocation(
        slots,
        assets,
        replace(evidence, capability_version="registry-v2"),
        allow_repeat=True,
        seed=0,
        material_revisions={asset: 1 for asset in assets},
    )
    assert newest.input_hash != original.input_hash


def test_same_slot_key_with_changed_material_type_cannot_reuse_old_compatibility_graph():
    slots, assets, evidence = setup([3, 3], 2)
    changed = (replace(slots[0], asset_type="VIDEO"), slots[1])
    with pytest.raises(OrbitError) as failure:
        solve_allocation(
            changed,
            assets,
            evidence,
            allow_repeat=True,
            seed=0,
            material_revisions={asset: 1 for asset in assets},
        )
    assert failure.value.status == 503
