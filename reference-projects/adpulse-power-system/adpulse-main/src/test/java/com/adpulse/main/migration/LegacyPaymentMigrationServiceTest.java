package com.adpulse.main.migration;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.main.migration.LegacyPaymentMigrationModels.TargetUser;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class LegacyPaymentMigrationServiceTest {
    @Test
    void matchesNonDeletedMigrationUsersByTrimmedDisplayNameRegardlessOfStatus() {
        TargetUser departed = user(348L, "邹丹梅", 0);
        TargetUser active = user(254L, "陈艳霞", 1);

        Map<String, List<TargetUser>> users =
                LegacyPaymentMigrationService.usersByDisplayName(List.of(departed, active));

        assertThat(LegacyPaymentMigrationService.uniqueUser(users, "  邹丹梅 ")).isSameAs(departed);
        assertThat(LegacyPaymentMigrationService.uniqueActiveUser(users, "陈艳霞")).isSameAs(active);
        assertThat(LegacyPaymentMigrationService.uniqueActiveUser(users, "邹丹梅")).isNull();
    }

    @Test
    void refusesAmbiguousDisplayNames() {
        TargetUser first = user(1L, "同名用户", 1);
        TargetUser second = user(2L, "同名用户", 1);
        Map<String, List<TargetUser>> users =
                LegacyPaymentMigrationService.usersByDisplayName(List.of(first, second));

        assertThat(LegacyPaymentMigrationService.uniqueUser(users, "同名用户")).isNull();
        assertThat(LegacyPaymentMigrationService.uniqueActiveUser(users, "同名用户")).isNull();
    }

    private static TargetUser user(long id, String displayName, int status) {
        return new TargetUser(id, null, displayName, displayName, null, status, null, null);
    }
}
