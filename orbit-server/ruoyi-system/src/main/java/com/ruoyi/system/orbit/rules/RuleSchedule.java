package com.ruoyi.system.orbit.rules;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.stereotype.Component;

/** 规则预览与未来Worker共用的无副作用调度核心；不创建运行、命中或分析任务。 */
@Component
public final class RuleSchedule {
    private static final Set<String> FIELDS =
            Set.of(
                    "frequency",
                    "interval_minutes",
                    "time_of_day",
                    "weekday",
                    "timezone",
                    "start_date",
                    "end_date");

    public enum Frequency {
        INTERVAL,
        DAILY,
        WEEKLY
    }

    /** 构造入口也校验互斥与范围，防止内部调用绕过JSON字段校验。星期使用ISO：周一1至周日7。 */
    public record Definition(
            Frequency frequency,
            Integer intervalMinutes,
            LocalTime timeOfDay,
            Integer weekday,
            ZoneId zone,
            LocalDate startDate,
            LocalDate endDate) {
        public Definition {
            if (frequency == null
                    || zone == null
                    || !ZoneId.getAvailableZoneIds().contains(zone.getId())
                    || startDate == null
                    || endDate == null
                    || startDate.getYear() < 1
                    || endDate.getYear() > 9999
                    || endDate.isBefore(startDate)
                    || ChronoUnit.DAYS.between(startDate, endDate) >= 366) throw invalid();
            boolean valid =
                    switch (frequency) {
                        case INTERVAL ->
                                intervalMinutes != null
                                        && intervalMinutes >= 15
                                        && intervalMinutes <= 1440
                                        && timeOfDay == null
                                        && weekday == null;
                        case DAILY ->
                                intervalMinutes == null && timeOfDay != null && weekday == null;
                        case WEEKLY ->
                                intervalMinutes == null
                                        && timeOfDay != null
                                        && weekday != null
                                        && weekday >= 1
                                        && weekday <= 7;
                    };
            if (!valid
                    || (timeOfDay != null
                            && (timeOfDay.getSecond() != 0 || timeOfDay.getNano() != 0)))
                throw invalid();
        }
    }

    /** 跳过的当地墙钟单列供未来运行审计；不可把不存在的时刻平移成另一个触发时刻。 */
    public record Preview(List<Instant> slots, List<LocalDateTime> skippedLocalTimes) {
        public Preview {
            slots = List.copyOf(slots);
            skippedLocalTimes = List.copyOf(skippedLocalTimes);
        }
    }

    /** 停机恢复只选择最近有效slot，其余记录为遗漏；该结果不是数据库租约或持久化去重。 */
    public record Due(
            Optional<Instant> slot, long missedSlots, List<LocalDateTime> skippedLocalTimes) {
        public Due {
            skippedLocalTimes = List.copyOf(skippedLocalTimes);
        }
    }

    /** 严格匹配产品Schedule字段；不接受数字字符串、额外属性、缺失的显式null或偏移量假时区。 */
    public Definition parse(JsonNode input) {
        if (input == null || !input.isObject() || input.size() != FIELDS.size()) throw invalid();
        input.fieldNames()
                .forEachRemaining(
                        name -> {
                            if (!FIELDS.contains(name)) throw invalid();
                        });
        try {
            Frequency frequency = Frequency.valueOf(text(input, "frequency"));
            Integer interval = nullableInteger(input.get("interval_minutes"));
            Integer weekday = nullableInteger(input.get("weekday"));
            JsonNode time = input.get("time_of_day");
            if (time == null
                    || (!time.isNull()
                            && (!time.isTextual()
                                    || !time.textValue().matches("([01][0-9]|2[0-3]):[0-5][0-9]"))))
                throw invalid();
            String zone = text(input, "timezone");
            if (zone.length() > 64 || !ZoneId.getAvailableZoneIds().contains(zone)) throw invalid();
            String start = text(input, "start_date"), end = text(input, "end_date");
            if (!start.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}")
                    || !end.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}")) throw invalid();
            return new Definition(
                    frequency,
                    interval,
                    time.isNull() ? null : LocalTime.parse(time.textValue()),
                    weekday,
                    ZoneId.of(zone),
                    LocalDate.parse(start),
                    LocalDate.parse(end));
        } catch (IllegalArgumentException | DateTimeException error) {
            throw invalid();
        }
    }

    /** 返回严格晚于afterExclusive的未来位置。数量上限50，整个生效区间最多366个当地日。 */
    public Preview preview(Definition schedule, Instant afterExclusive, int limit) {
        if (schedule == null || afterExclusive == null || limit < 1 || limit > 50) throw invalid();
        List<Instant> slots = new ArrayList<>();
        List<LocalDateTime> skipped = new ArrayList<>();
        if (schedule.frequency() == Frequency.INTERVAL) {
            Instant anchor = anchor(schedule), end = endExclusive(schedule);
            long step = schedule.intervalMinutes() * 60L;
            long index =
                    afterExclusive.isBefore(anchor)
                            ? 0
                            : Math.floorDiv(
                                            Duration.between(anchor, afterExclusive).getSeconds(),
                                            step)
                                    + 1;
            // 先用有界结束时间排除极远的查询，避免超范围Instant的乘法溢出。
            if (!afterExclusive.isBefore(end)) return new Preview(slots, skipped);
            Instant candidate = anchor.plusSeconds(index * step);
            while (candidate.isBefore(end) && slots.size() < limit) {
                slots.add(candidate);
                candidate = candidate.plusSeconds(step);
            }
        } else {
            for (LocalDate day = schedule.startDate();
                    !day.isAfter(schedule.endDate()) && slots.size() < limit;
                    day = day.plusDays(1)) {
                if (!matchesWeekday(schedule, day)) continue;
                LocalDateTime wall = day.atTime(schedule.timeOfDay());
                List<ZoneOffset> offsets = schedule.zone().getRules().getValidOffsets(wall);
                if (offsets.isEmpty()) {
                    if (schedule.zone()
                            .getRules()
                            .getTransition(wall)
                            .getInstant()
                            .isAfter(afterExclusive)) skipped.add(wall);
                } else {
                    // 重复墙钟统一选第一次（较早Instant）；预览/Worker不可各自选择不同offset。
                    Instant candidate = wall.toInstant(offsets.getFirst());
                    if (candidate.isAfter(afterExclusive)) slots.add(candidate);
                }
            }
        }
        return new Preview(slots, skipped);
    }

    /** 仅在规则启用且当前仍处于生效区间时补最近一次；不会对已过期规则补建分析。 */
    public Due latestDue(
            Definition schedule, Instant lastEvaluatedExclusive, Instant now, boolean enabled) {
        if (schedule == null
                || lastEvaluatedExclusive == null
                || now == null
                || now.isBefore(lastEvaluatedExclusive)) throw invalid();
        if (!enabled || now.isBefore(anchor(schedule)) || !now.isBefore(endExclusive(schedule)))
            return new Due(Optional.empty(), 0, List.of());
        Instant latest = null;
        long count = 0;
        List<LocalDateTime> skipped = new ArrayList<>();
        if (schedule.frequency() == Frequency.INTERVAL) {
            Instant anchor = anchor(schedule);
            long step = schedule.intervalMinutes() * 60L;
            long first =
                    lastEvaluatedExclusive.isBefore(anchor)
                            ? 0
                            : Math.floorDiv(
                                            Duration.between(anchor, lastEvaluatedExclusive)
                                                    .getSeconds(),
                                            step)
                                    + 1;
            long last = Math.floorDiv(Duration.between(anchor, now).getSeconds(), step);
            if (last >= first) {
                count = last - first + 1;
                latest = anchor.plusSeconds(last * step);
            }
        } else {
            for (LocalDate day = schedule.startDate();
                    !day.isAfter(schedule.endDate());
                    day = day.plusDays(1)) {
                if (!matchesWeekday(schedule, day)) continue;
                LocalDateTime wall = day.atTime(schedule.timeOfDay());
                List<ZoneOffset> offsets = schedule.zone().getRules().getValidOffsets(wall);
                Instant candidate =
                        offsets.isEmpty()
                                ? schedule.zone().getRules().getTransition(wall).getInstant()
                                : wall.toInstant(offsets.getFirst());
                if (candidate.isAfter(lastEvaluatedExclusive) && !candidate.isAfter(now)) {
                    if (offsets.isEmpty()) skipped.add(wall);
                    else {
                        count++;
                        latest = candidate;
                    }
                }
            }
        }
        return new Due(Optional.ofNullable(latest), Math.max(0, count - 1), skipped);
    }

    private boolean matchesWeekday(Definition schedule, LocalDate day) {
        return schedule.frequency() != Frequency.WEEKLY
                || day.getDayOfWeek().getValue() == schedule.weekday();
    }

    // 生效日午夜不存在时，锚点取该日首个有效时刻；整个当地日不存在时自然没有墙钟slot。
    private Instant anchor(Definition schedule) {
        return schedule.startDate().atStartOfDay(schedule.zone()).toInstant();
    }

    private Instant endExclusive(Definition schedule) {
        return schedule.endDate().plusDays(1).atStartOfDay(schedule.zone()).toInstant();
    }

    private static String text(JsonNode input, String field) {
        JsonNode value = input.get(field);
        if (value == null || !value.isTextual()) throw invalid();
        return value.textValue();
    }

    private static Integer nullableInteger(JsonNode value) {
        if (value == null
                || (!value.isNull() && (!value.isIntegralNumber() || !value.canConvertToInt())))
            throw invalid();
        return value.isNull() ? null : value.intValue();
    }

    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("规则调度字段、时间范围或查询参数无效");
    }
}
