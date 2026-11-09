package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.system.asset.lifecycle.AssetLifecycleEvent;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class AssetLifecycleTimelineTest {

    @Test
    void shouldPairAssignmentAndReleaseIntoUsagePeriod() {
        var assignedAt = LocalDateTime.of(2026, 9, 1, 9, 0);
        var releasedAt = LocalDateTime.of(2026, 9, 3, 18, 0);
        var periods =
                AssetLifecycleTimeline.usagePeriods(
                        List.of(
                                AssetLifecycleEvent.usage("ASSIGNED", "7", "王敏", assignedAt),
                                AssetLifecycleEvent.usage("RELEASED", "7", "王敏", releasedAt)));

        assertThat(periods)
                .singleElement()
                .satisfies(
                        period -> {
                            assertThat(period.userName()).isEqualTo("王敏");
                            assertThat(period.startedAt()).isEqualTo(assignedAt);
                            assertThat(period.endedAt()).isEqualTo(releasedAt);
                            assertThat(period.status()).isEqualTo("RELEASED");
                        });
    }
}
