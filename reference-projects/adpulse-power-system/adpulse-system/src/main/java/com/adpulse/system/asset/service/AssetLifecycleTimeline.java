package com.adpulse.system.asset.service;

import com.adpulse.system.asset.lifecycle.AssetLifecycleEvent;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** 将按时间记录的使用人事件折叠为页面展示所需的使用区间。 */
public final class AssetLifecycleTimeline {
    private AssetLifecycleTimeline() {}

    public record UsagePeriod(
            String userId,
            String userName,
            LocalDateTime startedAt,
            LocalDateTime endedAt,
            String status) {}

    public static List<UsagePeriod> usagePeriods(List<AssetLifecycleEvent> events) {
        Map<String, AssetLifecycleEvent> activeAssignments = new HashMap<>();
        List<UsagePeriod> periods = new ArrayList<>();
        events.stream()
                .filter(event -> event.userId() != null && !event.userId().isBlank())
                .sorted(Comparator.comparing(AssetLifecycleEvent::occurredAt))
                .forEach(
                        event -> {
                            if ("ASSIGNED".equals(event.eventType())) {
                                activeAssignments.put(event.userId(), event);
                                return;
                            }
                            if (!"RELEASED".equals(event.eventType())) return;
                            AssetLifecycleEvent assigned = activeAssignments.remove(event.userId());
                            if (assigned == null) return;
                            periods.add(
                                    new UsagePeriod(
                                            assigned.userId(),
                                            assigned.userName(),
                                            assigned.occurredAt(),
                                            event.occurredAt(),
                                            "RELEASED"));
                        });
        activeAssignments.values().stream()
                .sorted(Comparator.comparing(AssetLifecycleEvent::occurredAt))
                .forEach(
                        assigned ->
                                periods.add(
                                        new UsagePeriod(
                                                assigned.userId(),
                                                assigned.userName(),
                                                assigned.occurredAt(),
                                                null,
                                                "ACTIVE")));
        return periods;
    }
}
