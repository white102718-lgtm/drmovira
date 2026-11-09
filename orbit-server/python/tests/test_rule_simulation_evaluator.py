"""S1纯计算/流完整性；不证明模拟来源、SQL、15分钟资格或业务启用。"""

import asyncio
import hashlib
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from uuid import UUID

import pytest
from test_rule_contract import parse, sample_rule

import orbit_api.rule_simulation_evaluator as core
from orbit_api.directory_tokens import canonical
from orbit_api.metrics_aggregation import MetricAccumulator, MetricGroup
from orbit_api.rule_contract import ConditionResult, parse_rule_response


def uid(n):
    return str(UUID(int=n))


def frame(value):
    # 独立固定协议参考，不调用被测frame/hash helper。
    body = canonical(value).encode("utf-8")
    return len(body).to_bytes(8, "big") + body


def expected_root(ids):
    value = hashlib.sha256(frame({"domain": "ORBIT_RULE_SIMULATION_ENTITY_IDS_V1", "version": 1}))
    for identity in ids:
        value.update(frame(identity))
    value.update(frame({"count": len(ids)}))
    return value.hexdigest()


def expected(items):
    ids = [item.entity_id for item in items]
    return core.ExpectedEntityStream(len(ids), expected_root(ids))


def entity(number=1, *, metrics=None, currency="USD", account=None):
    return core.EntityObservation(uid(number), account or uid(1000), currency, metrics or {})


def rule(*, metric="spend", operator="GTE", threshold="10"):
    value = sample_rule()
    value["groups"][0]["conditions"][0].update(
        metric=metric, operator=operator, threshold=threshold
    )
    return parse(value)


async def stream(items, size=20):
    for index in range(0, len(items), size):
        yield tuple(items[index : index + size])


async def run(items, *, selected=None, size=20, expectation=None):
    output = []

    async def sink(batch):
        output.extend(batch)

    summary = await core.evaluate_simulation_entities(
        selected or rule(), expectation or expected(items), stream(items, size), sink
    )
    return summary, output


@pytest.mark.asyncio
async def test_complete_original_five_fields_counts_and_independent_framed_root():
    items = [
        entity(1, metrics={"spend": "10.000000"}),
        entity(2, metrics={"spend": "9"}),
        entity(3),
    ]
    summary, output = await run(items)
    assert (
        summary.scanned_count,
        summary.hit_count,
        summary.false_count,
        summary.unknown_count,
    ) == (3, 1, 1, 1)
    assert summary.condition_count == 3
    assert [item.result for item in output] == ["TRUE", "FALSE", "UNKNOWN"]
    leaves = [item.conditions[0].public() for item in output]
    for leaf in leaves:
        assert set(leaf) == {"entity_id", "condition_index", "value", "result", "reason_code"}
        assert parse_rule_response(ConditionResult, leaf).model_dump() == leaf
    assert leaves[0]["value"] == "10" and leaves[-1]["value"] is None
    assert summary.entity_ids_root == expected_root([uid(1), uid(2), uid(3)])
    root = hashlib.sha256(frame({"domain": "ORBIT_RULE_SIMULATION_RESULTS_V1", "version": 1}))
    rule_hash = hashlib.sha256(canonical(rule().model_dump()).encode()).hexdigest()
    root.update(
        frame(
            {
                "algorithm": core.ALGORITHM_VERSION,
                "rule_hash": rule_hash,
                "expected_count": 3,
                "entity_ids_root": summary.entity_ids_root,
            }
        )
    )
    for item, leaf in zip(items, leaves, strict=True):
        root.update(
            frame(
                {
                    "entity_id": item.entity_id,
                    "account_id": item.account_id,
                    "currency": item.currency,
                    "result": leaf["result"],
                    "conditions": [leaf],
                }
            )
        )
    root.update(
        frame(
            {
                "summary": {
                    "scanned_count": 3,
                    "hit_count": 1,
                    "unknown_count": 1,
                    "false_count": 1,
                    "condition_count": 3,
                }
            }
        )
    )
    assert summary.results_root == root.hexdigest() and summary.rule_hash == rule_hash
    assert not hasattr(summary, "eligible") and not hasattr(summary, "expires_at")


@pytest.mark.asyncio
async def test_full_leaf_index_not_short_circuited_and_entity_not_leaf_statistics():
    selected = sample_rule()
    selected["groups"] = [
        {
            "logic": "AND",
            "conditions": [
                {"metric": "spend", "operator": "GT", "threshold": "10"},
                {"metric": "clicks", "operator": "NEQ", "threshold": "0"},
            ],
        },
        {"logic": "OR", "conditions": [{"metric": "ctr", "operator": "GT", "threshold": "0"}]},
    ]
    summary, output = await run(
        [entity(metrics={"spend": "0", "ctr": "1"})], selected=parse(selected)
    )
    assert summary.false_count == 1 and summary.condition_count == 3
    assert [v.condition_index for v in output[0].conditions] == [0, 1, 2]
    assert [v.result for v in output[0].conditions] == ["FALSE", "UNKNOWN", "TRUE"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value", [None, "NaN", "01", Decimal("NaN"), Decimal("-1"), Decimal("1E+999999")]
)
async def test_unknown_not_zero_and_no_giant_decimal_expansion(value):
    summary, output = await run(
        [entity(metrics={"spend": value})], selected=rule(operator="NEQ", threshold="0")
    )
    assert summary.unknown_count == 1 and output[0].conditions[0].value is None


@pytest.mark.asyncio
async def test_ratio_real_numerators_not_average_and_zero_denominator_unknown():
    group = MetricGroup(uid(800), "USD", uid(801), "v1")
    aggregate = MetricAccumulator(group)
    for spend, value in (("10", "30"), ("90", "0")):
        aggregate.add(
            group,
            {
                "spend": spend,
                "purchase_value": value,
                "impressions": "0",
                "clicks": "0",
                "registrations": "0",
                "purchases": "0",
            },
        )
    metrics = aggregate.finish(ratios_allowed=True)
    assert metrics["roas"] == "0.3" and metrics["ctr"] is None
    summary, output = await run(
        [entity(metrics={"roas": metrics["roas"]})],
        selected=rule(metric="roas", operator="GT", threshold="1"),
    )
    assert summary.false_count == 1 and output[0].conditions[0].value == "0.3"
    summary, _ = await run(
        [entity(metrics={"ctr": metrics["ctr"]})],
        selected=rule(metric="ctr", operator="NEQ", threshold="0"),
    )
    assert summary.unknown_count == 1


@pytest.mark.asyncio
async def test_money_currencies_independent_unknown_currency_not_usd_or_all_metrics_missing():
    items = [
        entity(1, metrics={"spend": "11"}, currency="USD"),
        entity(2, metrics={"spend": "9"}, currency="EUR"),
        entity(3, metrics={"spend": "100"}, currency=None),
    ]
    summary, output = await run(items)
    assert [value.result for value in output] == ["TRUE", "FALSE", "UNKNOWN"]
    assert (summary.hit_count, summary.false_count, summary.unknown_count) == (1, 1, 1)
    summary, _ = await run(
        [entity(metrics={"clicks": "10"}, currency=None)], selected=rule(metric="clicks")
    )
    assert summary.hit_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [1, 20, 50, 100, 200])
async def test_same_ordered_stream_batch_boundaries_do_not_change_roots(size):
    items = [entity(index, metrics={"spend": str(index)}) for index in range(1, 222)]
    original, _ = await run(items, size=200)
    current, _ = await run(items, size=size)
    assert current == original


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["rule", "entity", "account", "currency", "value"])
async def test_exact_root_binds_rule_entity_account_currency_and_results(change):
    original, _ = await run([entity(metrics={"spend": "10"})])
    item, selected = entity(metrics={"spend": "10"}), rule()
    if change == "rule":
        selected.name += "另一个规范配置"
    elif change == "entity":
        item = replace(item, entity_id=uid(2))
    elif change == "account":
        item = replace(item, account_id=uid(2000))
    elif change == "currency":
        item = replace(item, currency="EUR")
    else:
        item = replace(item, observations={"spend": "11"})
    changed, _ = await run([item], selected=selected)
    assert changed.results_root != original.results_root


def test_deep_freeze_copied_mapping_and_all_result_layers():
    raw = {"spend": "10"}
    item = entity(metrics=raw)
    raw["spend"] = "999"
    assert item.observations["spend"] == "10"
    with pytest.raises(TypeError):
        item.observations["spend"] = "123"
    with pytest.raises(FrozenInstanceError):
        item.entity_id = uid(99)
    assert not hasattr(item, "__dict__")


@pytest.mark.asyncio
async def test_sink_non_none_ack_is_not_treated_as_success():
    items = [entity()]

    async def sink(_batch):
        return False

    with pytest.raises(ValueError, match="SINK_ACK_INVALID"):
        await core.evaluate_simulation_entities(rule(), expected(items), stream(items), sink)


@pytest.mark.parametrize("identities", [[uid(2), uid(1)], [uid(1), uid(1)], ["invalid"]])
def test_identity_root_helper_requires_same_global_order_and_uuid_contract(identities):
    with pytest.raises(ValueError):
        core.entity_ids_root(iter(identities))


def test_identity_root_protocol_is_fixed_for_empty_and_multi_entity():
    assert core.entity_ids_root(()) == expected_root([])
    identities = [uid(1), uid(7), uid(100)]
    assert core.entity_ids_root(iter(identities)) == expected_root(identities)


@pytest.mark.asyncio
async def test_sink_cannot_mutate_frozen_leaf_or_change_hash_by_mutating_public_projection():
    items = [entity(metrics={"spend": "10"})]
    original, _ = await run(items)

    async def sink(batch):
        with pytest.raises(FrozenInstanceError):
            batch[0].conditions[0].value = "999"
        with pytest.raises(FrozenInstanceError):
            batch[0].conditions = ()
        copied = batch[0].conditions[0].public()
        copied["value"] = "999"

    current = await core.evaluate_simulation_entities(rule(), expected(items), stream(items), sink)
    assert current == original


@pytest.mark.asyncio
async def test_rule_mutation_after_stream_starts_not_retained():
    selected, items = rule(), [entity(metrics={"spend": "10"})]
    original, _ = await run(items, selected=selected)

    async def source():
        selected.groups[0].conditions[0].threshold = "999"
        yield tuple(items)

    async def sink(_batch):
        pass

    current = await core.evaluate_simulation_entities(selected, expected(items), source(), sink)
    assert current == original


@pytest.mark.asyncio
async def test_explicit_zero_is_only_complete_with_correct_empty_identity_root():
    summary, output = await run([])
    assert summary.scanned_count == summary.condition_count == 0 and output == []
    with pytest.raises(ValueError, match="INCOMPLETE_OR_ROOT"):
        await run([], expectation=core.ExpectedEntityStream(0, "0" * 64))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["missing_tail", "extra", "duplicate", "descending", "wrong_root"])
async def test_stream_identity_completeness_not_only_count(mode):
    items = [entity(1), entity(2)]
    expectation = expected(items)
    if mode == "missing_tail":
        items = items[:1]
    elif mode == "extra":
        items += [entity(3)]
    elif mode == "duplicate":
        items = [entity(1), entity(1)]
    elif mode == "descending":
        items.reverse()
    else:
        expectation = core.ExpectedEntityStream(2, expected_root([uid(3), uid(4)]))
    with pytest.raises(ValueError):
        await run(items, expectation=expectation)


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [(), [], (entity(),) * 201, (object(),)])
async def test_batches_are_bounded_tuple_of_frozen_contract(batch):
    async def source():
        yield batch

    async def sink(_):
        raise AssertionError("INVALID_BATCH_REACHED_SINK")

    with pytest.raises(ValueError):
        await core.evaluate_simulation_entities(rule(), expected([]), source(), sink)


@pytest.mark.parametrize("count", [-1, True, 2147483648, "1"])
def test_original_32bit_scanned_exact_range_no_truncation(count):
    with pytest.raises(ValueError):
        core.ExpectedEntityStream(count, expected_root([]))
    assert core.ExpectedEntityStream(2147483647, expected_root([])).entity_count == 2147483647


@pytest.mark.parametrize(
    "data",
    [
        {"entity_id": "BAD"},
        {"account_id": "BAD"},
        {"entity_id": uid(1).upper().replace("00000000", "AAAAAAAA", 1)},
        {"currency": "usd"},
        {"currency": ""},
        {"observations": {"usage": "1"}},
        {"observations": {"spend": 1}},
        {"observations": {"spend": 1.0}},
        {"observations": {"spend": ["1"]}},
    ],
)
def test_input_metadata_and_observation_type_boundary(data):
    values = {"entity_id": uid(1), "account_id": uid(100), "currency": "USD", "observations": {}}
    with pytest.raises(ValueError):
        core.EntityObservation(**(values | data))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["source", "sink", "cancel_source", "cancel_sink", "cancel_eof"]
)
async def test_any_failure_or_cancellation_no_summary_and_no_false_sink_rollback(failure):
    items, staged, returned = [entity(1), entity(2)], [], []

    async def source():
        yield (items[0],)
        if failure == "source":
            raise RuntimeError("SOURCE_FAILED")
        if failure == "cancel_source":
            raise asyncio.CancelledError
        yield (items[1],)
        if failure == "cancel_eof":
            asyncio.current_task().cancel()

    async def sink(batch):
        staged.extend(batch)
        if failure == "sink":
            raise RuntimeError("SINK_FAILED")
        if failure == "cancel_sink":
            raise asyncio.CancelledError

    async def execute():
        returned.append(
            await core.evaluate_simulation_entities(rule(), expected(items), source(), sink)
        )

    task = asyncio.create_task(execute())
    with pytest.raises(asyncio.CancelledError if failure.startswith("cancel") else RuntimeError):
        await task
    assert returned == [] and len(staged) >= 1


@pytest.mark.asyncio
async def test_each_bounded_batch_cooperatively_observes_cancel_without_unbounded_run():
    consumed = 0

    async def source():
        for index in range(1, 1001):
            yield (entity(index),)

    async def sink(_):
        nonlocal consumed
        consumed += 1
        if consumed == 1:
            asyncio.current_task().cancel()

    task = asyncio.create_task(
        core.evaluate_simulation_entities(
            rule(),
            core.ExpectedEntityStream(1000, expected_root([uid(i) for i in range(1, 1001)])),
            source(),
            sink,
        )
    )
    with pytest.raises(asyncio.CancelledError):
        await task
    assert consumed == 1
