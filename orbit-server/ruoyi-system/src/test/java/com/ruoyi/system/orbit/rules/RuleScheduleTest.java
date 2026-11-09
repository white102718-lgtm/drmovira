package com.ruoyi.system.orbit.rules;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 确定时间实例覆盖真实时区规则，无系统时钟、数据库、网络或定时等待依赖。 */
class RuleScheduleTest {
    private final ObjectMapper json = new ObjectMapper();
    private final RuleSchedule engine = new RuleSchedule();

    private ObjectNode request(String frequency, String zone, String start, String end) {
        ObjectNode value = json.createObjectNode();
        value.put("frequency", frequency)
                .put("timezone", zone)
                .put("start_date", start)
                .put("end_date", end);
        value.putNull("interval_minutes");
        value.putNull("time_of_day");
        value.putNull("weekday");
        if (frequency.equals("INTERVAL")) value.put("interval_minutes", 60);
        else value.put("time_of_day", "09:00");
        if (frequency.equals("WEEKLY")) value.put("weekday", 1);
        return value;
    }

    private RuleSchedule.Definition daily(String zone, String start, String end, String time) {
        return engine.parse(request("DAILY", zone, start, end).put("time_of_day", time));
    }

    private Instant at(String value) {
        return Instant.parse(value);
    }

    @Test
    void fieldsMatchUntouchedProductScheduleContract() throws Exception {
        var contract =
                json.readTree(
                        Files.readString(
                                Path.of("../docs/orbit/baseline/contracts/openapi-current.json")));
        // Maven模块测试工作目录在ruoyi-system，回到仓库读取只读产品基线。
        var schema = contract.path("components").path("schemas").path("Schedule");
        Set<String> properties = new HashSet<>();
        schema.path("properties").fieldNames().forEachRemaining(properties::add);
        assertEquals(
                properties,
                new HashSet<>(
                        json.convertValue(
                                        request("DAILY", "UTC", "2026-01-01", "2026-01-01"),
                                        Map.class)
                                .keySet()));
        assertEquals(
                properties, new HashSet<>(json.convertValue(schema.path("required"), List.class)));
        assertFalse(schema.path("additionalProperties").asBoolean());
    }

    @ParameterizedTest
    @ValueSource(strings = {"INTERVAL", "DAILY", "WEEKLY"})
    void acceptsEachExclusiveFrequency(String frequency) {
        assertEquals(
                frequency,
                engine.parse(request(frequency, "Asia/Shanghai", "2026-11-01", "2026-11-30"))
                        .frequency()
                        .name());
    }

    @ParameterizedTest
    @ValueSource(ints = {14, 1441, -1, 0})
    void rejectsIntervalOutsideContract(int minutes) {
        assertThrows(
                IllegalArgumentException.class,
                () ->
                        engine.parse(
                                request("INTERVAL", "UTC", "2026-01-01", "2026-01-01")
                                        .put("interval_minutes", minutes)));
    }

    @ParameterizedTest
    @ValueSource(ints = {15, 1440})
    void acceptsBothIntervalBoundaries(int minutes) {
        assertEquals(
                minutes,
                engine.parse(
                                request("INTERVAL", "UTC", "2026-01-01", "2026-01-01")
                                        .put("interval_minutes", minutes))
                        .intervalMinutes());
    }

    @Test
    void rejectsInactiveFrequencyFieldsAndMissingExplicitNull() {
        ObjectNode value = request("DAILY", "UTC", "2026-01-01", "2026-01-01");
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.parse(value.deepCopy().put("interval_minutes", 60)));
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.parse(value.deepCopy().put("weekday", 1)));
        ObjectNode absent = value.deepCopy();
        absent.remove("interval_minutes");
        assertThrows(IllegalArgumentException.class, () -> engine.parse(absent));
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.parse(value.deepCopy().put("unexpected", "opaque-private-input")));
        assertThrows(
                IllegalArgumentException.class,
                () ->
                        engine.parse(
                                request("INTERVAL", "UTC", "2026-01-01", "2026-01-01")
                                        .put("time_of_day", "12:00")));
        assertThrows(
                IllegalArgumentException.class,
                () ->
                        engine.parse(
                                request("WEEKLY", "UTC", "2026-01-01", "2026-01-01")
                                        .putNull("weekday")));
    }

    @Test
    void rejectsCoercionUnknownEnumAndNullStructureWithoutEcho() {
        ObjectNode value = request("INTERVAL", "UTC", "2026-01-01", "2026-01-01");
        for (ObjectNode bad :
                List.of(
                        value.deepCopy().put("interval_minutes", "60"),
                        value.deepCopy().put("interval_minutes", 60.0),
                        value.deepCopy().put("interval_minutes", Long.MAX_VALUE),
                        value.deepCopy().put("frequency", "private-unknown-frequency"))) {
            var error = assertThrows(IllegalArgumentException.class, () -> engine.parse(bad));
            assertEquals("规则调度字段、时间范围或查询参数无效", error.getMessage());
        }
        assertThrows(IllegalArgumentException.class, () -> engine.parse(null));
        assertThrows(IllegalArgumentException.class, () -> engine.parse(json.createArrayNode()));
    }

    @ParameterizedTest
    @ValueSource(strings = {"24:00", "9:00", "09:60", "09:00:00", "", " 09:00"})
    void rejectsInvalidWallClock(String time) {
        assertThrows(
                IllegalArgumentException.class,
                () -> daily("UTC", "2026-01-01", "2026-01-01", time));
    }

    @ParameterizedTest
    @ValueSource(strings = {"+08:00", "GMT+08:00", "Mars/Private", "", " Asia/Shanghai"})
    void rejectsOffsetsAndUnknownZone(String zone) {
        assertThrows(
                IllegalArgumentException.class,
                () -> daily(zone, "2026-01-01", "2026-01-01", "09:00"));
    }

    @Test
    void validatesLeapDateAndInclusive366DayMaximum() {
        assertNotNull(daily("UTC", "2024-01-01", "2024-12-31", "09:00"));
        assertThrows(
                IllegalArgumentException.class,
                () -> daily("UTC", "2024-01-01", "2025-01-01", "09:00"));
        assertThrows(
                IllegalArgumentException.class,
                () -> daily("UTC", "2025-02-29", "2025-03-01", "09:00"));
        assertThrows(
                IllegalArgumentException.class,
                () -> daily("UTC", "2026-01-02", "2026-01-01", "09:00"));
        assertThrows(
                IllegalArgumentException.class,
                () -> daily("UTC", "2026-1-01", "2026-01-01", "09:00"));
        assertThrows(
                IllegalArgumentException.class,
                () -> daily("UTC", "0000-01-01", "0000-01-01", "09:00"));
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 8, -1})
    void validatesIsoWeekday(int weekday) {
        assertThrows(
                IllegalArgumentException.class,
                () ->
                        engine.parse(
                                request("WEEKLY", "UTC", "2026-01-01", "2026-01-31")
                                        .put("weekday", weekday)));
    }

    @Test
    void includesBothBoundaryDaysAndExcludesExactPriorSlot() {
        var schedule = daily("Asia/Shanghai", "2026-11-01", "2026-11-02", "09:00");
        assertEquals(
                List.of(at("2026-11-01T01:00:00Z"), at("2026-11-02T01:00:00Z")),
                engine.preview(schedule, at("2026-10-31T23:00:00Z"), 50).slots());
        assertEquals(
                List.of(at("2026-11-02T01:00:00Z")),
                engine.preview(schedule, at("2026-11-01T01:00:00Z"), 50).slots());
        assertTrue(engine.preview(schedule, at("2026-11-02T01:00:00Z"), 1).slots().isEmpty());
    }

    @Test
    void weeklyUsesIsoMondayAndSundayAcrossUtcDateBoundary() {
        ObjectNode monday =
                request("WEEKLY", "Asia/Shanghai", "2026-11-01", "2026-11-09")
                        .put("time_of_day", "00:15");
        assertEquals(
                List.of(at("2026-11-01T16:15:00Z"), at("2026-11-08T16:15:00Z")),
                engine.preview(engine.parse(monday), at("2026-10-30T00:00:00Z"), 50).slots());
        assertEquals(
                List.of(at("2026-10-31T16:15:00Z"), at("2026-11-07T16:15:00Z")),
                engine.preview(
                                engine.parse(monday.put("weekday", 7)),
                                at("2026-10-30T00:00:00Z"),
                                50)
                        .slots());
    }

    @Test
    void springGapIsSkippedWithoutMovingToThreeThirty() {
        var schedule = daily("America/New_York", "2026-03-07", "2026-03-09", "02:30");
        var preview = engine.preview(schedule, at("2026-03-07T00:00:00Z"), 50);
        assertEquals(
                List.of(at("2026-03-07T07:30:00Z"), at("2026-03-09T06:30:00Z")), preview.slots());
        assertEquals(List.of(LocalDateTime.parse("2026-03-08T02:30")), preview.skippedLocalTimes());
        var due =
                engine.latestDue(
                        schedule, at("2026-03-07T07:30:00Z"), at("2026-03-08T08:00:00Z"), true);
        assertTrue(due.slot().isEmpty());
        assertEquals(preview.skippedLocalTimes(), due.skippedLocalTimes());
    }

    @Test
    void fallOverlapSelectsFirstOccurrenceOnlyForPreviewAndDue() {
        var schedule = daily("America/New_York", "2026-11-01", "2026-11-02", "01:30");
        assertEquals(
                List.of(at("2026-11-01T05:30:00Z"), at("2026-11-02T06:30:00Z")),
                engine.preview(schedule, at("2026-11-01T00:00:00Z"), 50).slots());
        assertEquals(
                at("2026-11-01T05:30:00Z"),
                engine.latestDue(
                                schedule,
                                at("2026-11-01T00:00:00Z"),
                                at("2026-11-01T06:45:00Z"),
                                true)
                        .slot()
                        .orElseThrow());
        assertTrue(
                engine.latestDue(
                                schedule,
                                at("2026-11-01T05:30:00Z"),
                                at("2026-11-01T06:45:00Z"),
                                true)
                        .slot()
                        .isEmpty());
        assertEquals(
                List.of(at("2026-11-02T06:30:00Z")),
                engine.preview(schedule, at("2026-11-01T05:45:00Z"), 50).slots());
    }

    @Test
    void handlesHalfHourDstAndEntireMissingLocalDay() {
        var lordHowe = daily("Australia/Lord_Howe", "2026-10-04", "2026-10-04", "02:15");
        assertTrue(engine.preview(lordHowe, at("2026-10-02T00:00:00Z"), 50).slots().isEmpty());
        assertEquals(
                List.of(LocalDateTime.parse("2026-10-04T02:15")),
                engine.preview(lordHowe, at("2026-10-02T00:00:00Z"), 50).skippedLocalTimes());
        var apia = daily("Pacific/Apia", "2011-12-29", "2011-12-31", "09:00");
        var preview = engine.preview(apia, at("2011-12-28T00:00:00Z"), 50);
        assertEquals(
                List.of(at("2011-12-29T19:00:00Z"), at("2011-12-30T19:00:00Z")), preview.slots());
        assertEquals(List.of(LocalDateTime.parse("2011-12-30T09:00")), preview.skippedLocalTimes());
    }

    @Test
    void intervalUsesElapsedMinutesAcrossBothDstTransitions() {
        for (String date : List.of("2026-03-08", "2026-11-01")) {
            var schedule = engine.parse(request("INTERVAL", "America/New_York", date, date));
            List<Instant> slots = engine.preview(schedule, at(date + "T00:00:00Z"), 50).slots();
            assertEquals(date.contains("03-") ? 23 : 25, slots.size());
            for (int i = 1; i < slots.size(); i++)
                assertEquals(Duration.ofHours(1), Duration.between(slots.get(i - 1), slots.get(i)));
        }
    }

    @Test
    void intervalDoesNotResetAnchorEachLocalMidnight() {
        var schedule =
                engine.parse(
                        request("INTERVAL", "UTC", "2026-01-01", "2026-01-02")
                                .put("interval_minutes", 1000));
        assertEquals(
                List.of(
                        at("2026-01-01T00:00:00Z"),
                        at("2026-01-01T16:40:00Z"),
                        at("2026-01-02T09:20:00Z")),
                engine.preview(schedule, at("2025-12-31T23:59:59Z"), 50).slots());
    }

    @Test
    void downtimeCoalescesToLatestAndCountsMissedInsteadOfBurst() {
        var interval =
                engine.parse(
                        request("INTERVAL", "UTC", "2026-01-01", "2026-01-31")
                                .put("interval_minutes", 15));
        var due =
                engine.latestDue(
                        interval, at("2026-01-01T00:00:00Z"), at("2026-01-01T01:07:00Z"), true);
        assertEquals(at("2026-01-01T01:00:00Z"), due.slot().orElseThrow());
        assertEquals(3, due.missedSlots());
        var daily = daily("UTC", "2026-01-01", "2026-01-10", "09:00");
        due = engine.latestDue(daily, at("2026-01-01T09:00:00Z"), at("2026-01-04T10:00:00Z"), true);
        assertEquals(at("2026-01-04T09:00:00Z"), due.slot().orElseThrow());
        assertEquals(2, due.missedSlots());
        assertEquals(
                due.slot().orElseThrow(),
                engine.preview(daily, at("2026-01-03T09:00:00Z"), 1).slots().getFirst());
    }

    @Test
    void disabledExpiredAndNotStartedCannotSelectNewWork() {
        var schedule = daily("UTC", "2026-01-01", "2026-01-02", "09:00");
        Instant last = at("2025-12-31T00:00:00Z");
        assertTrue(
                engine.latestDue(schedule, last, at("2026-01-01T10:00:00Z"), false)
                        .slot()
                        .isEmpty());
        assertTrue(
                engine.latestDue(schedule, last, at("2026-01-03T00:00:00Z"), true)
                        .slot()
                        .isEmpty());
        assertTrue(
                engine.latestDue(schedule, last, at("2025-12-31T23:59:59Z"), true)
                        .slot()
                        .isEmpty());
        assertEquals(
                at("2026-01-02T09:00:00Z"),
                engine.latestDue(schedule, last, at("2026-01-02T23:59:59Z"), true)
                        .slot()
                        .orElseThrow());
    }

    @Test
    void exactAndFractionalBoundariesAgreeWithoutDuplicateSlots() {
        var schedule = engine.parse(request("INTERVAL", "UTC", "2026-01-01", "2026-01-01"));
        Instant slot = at("2026-01-01T01:00:00Z");
        assertEquals(slot, engine.preview(schedule, slot.minusNanos(1), 1).slots().getFirst());
        assertEquals(slot.plusSeconds(3600), engine.preview(schedule, slot, 1).slots().getFirst());
        assertEquals(
                slot,
                engine.latestDue(schedule, slot.minusNanos(1), slot, true).slot().orElseThrow());
        assertTrue(engine.latestDue(schedule, slot, slot, true).slot().isEmpty());
    }

    @Test
    void validatesDirectConstructionAndReturnsImmutableBoundedResults() {
        var schedule = daily("UTC", "2026-01-01", "2026-12-31", "09:00");
        assertThrows(
                IllegalArgumentException.class,
                () ->
                        new RuleSchedule.Definition(
                                RuleSchedule.Frequency.DAILY,
                                60,
                                LocalTime.NOON,
                                null,
                                ZoneId.of("UTC"),
                                LocalDate.of(2026, 1, 1),
                                LocalDate.of(2026, 1, 2)));
        assertEquals(50, engine.preview(schedule, Instant.MIN, 50).slots().size());
        assertThrows(
                UnsupportedOperationException.class,
                () -> engine.preview(schedule, Instant.MIN, 1).slots().clear());
        assertThrows(
                IllegalArgumentException.class, () -> engine.preview(schedule, Instant.MIN, 0));
        assertThrows(
                IllegalArgumentException.class, () -> engine.preview(schedule, Instant.MIN, 51));
        assertThrows(
                IllegalArgumentException.class,
                () -> engine.latestDue(schedule, Instant.MAX, Instant.MIN, true));
        assertTrue(engine.preview(schedule, Instant.MAX, 1).slots().isEmpty());
    }
}
