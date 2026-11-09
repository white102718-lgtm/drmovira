package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import com.adpulse.main.adaccountasset.AdAccountAssetViews.Account;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.Assignment;
import com.adpulse.main.channel.mapper.ChannelMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.transaction.annotation.Transactional;

class AdAccountAssetAuditTest {
    private final AdAccountAssetService service =
            new AdAccountAssetService(
                    mock(MongoTemplate.class),
                    mock(AdAccountAssetMapper.class),
                    mock(AdAccountAssetAssignmentMapper.class),
                    mock(AccountAttributeMapper.class),
                    mock(AdAccountUserMapper.class),
                    mock(ChannelMapper.class),
                    "fb_ad_accounts");

    @Test
    void recordsClearAsUnsetAndKeepsFullCardNumber() {
        Account before = account("1234 5678 9012 3456", "10", "渠道甲", List.of());
        Account after = account("", "10", "渠道甲", List.of());

        var changes = service.accountChanges(before, after);

        var card =
                changes.stream()
                        .filter(change -> change.fieldKey().equals("cardNumber"))
                        .findFirst()
                        .orElseThrow();
        assertThat(card.before().display()).isEqualTo("1234 5678 9012 3456");
        assertThat(card.after().display()).isNull();
    }

    @Test
    void ignoresNormalizedNoOpAndSnapshotsOptionIdWithName() {
        Account before = account("1234", "10", "渠道甲", List.of());
        assertThat(service.accountChanges(before, account("1234", "10", "渠道甲", List.of())))
                .isEmpty();

        var changes = service.accountChanges(before, account("1234", "11", "渠道乙", List.of()));
        var channel =
                changes.stream()
                        .filter(change -> change.fieldKey().equals("channel"))
                        .findFirst()
                        .orElseThrow();
        assertThat(channel.before().references().getFirst().id()).isEqualTo("10");
        assertThat(channel.before().references().getFirst().name()).isEqualTo("渠道甲");
        assertThat(channel.after().references().getFirst().id()).isEqualTo("11");
        assertThat(channel.after().references().getFirst().name()).isEqualTo("渠道乙");
    }

    @Test
    void snapshotsMultipleUsageUsers() {
        Account before = account("1234", "10", "渠道甲", List.of());
        List<Assignment> assignments =
                List.of(
                        new Assignment("1", "101", "张三", true, "ACTIVE", "MANUAL", null, null),
                        new Assignment("2", "102", "李四", false, "ACTIVE", "MANUAL", null, null));

        var users =
                service.accountChanges(before, account("1234", "10", "渠道甲", assignments)).stream()
                        .filter(change -> change.fieldKey().equals("usageUsers"))
                        .findFirst()
                        .orElseThrow();

        assertThat(users.after().references()).extracting("id").containsExactly("101", "102");
    }

    @Test
    void initialSnapshotContainsOnlyConfiguredValuesAndPlatformStatusCode() {
        List<Assignment> assignments =
                List.of(new Assignment("1", "101", "张三", true, "ACTIVE", "MANUAL", null, null));

        var changes =
                service.accountInitialChanges(
                        account("1234 5678 9012 3456", "10", "渠道甲", assignments));

        assertThat(changes)
                .extracting("fieldKey")
                .contains(
                        "accountId",
                        "accountName",
                        "accountStatus",
                        "inventoryStatus",
                        "channel",
                        "cardNumber",
                        "usageUsers")
                .doesNotContain("remark", "timezone");
        var platformStatus =
                changes.stream()
                        .filter(change -> change.fieldKey().equals("accountStatus"))
                        .findFirst()
                        .orElseThrow();
        assertThat(platformStatus.after().display()).isEqualTo("正常");
        assertThat(platformStatus.after().references().getFirst().id()).isEqualTo("1");
    }

    @Test
    void updateEntrypointsKeepAuditWritesInsideBusinessTransactions() throws Exception {
        assertThat(
                        AdAccountAssetService.class
                                .getMethod(
                                        "update", String.class, AdAccountAssetRequests.Save.class)
                                .isAnnotationPresent(Transactional.class))
                .isTrue();
        assertThat(
                        AdAccountAssetService.class
                                .getMethod("batchUpdate", AdAccountAssetRequests.BatchUpdate.class)
                                .isAnnotationPresent(Transactional.class))
                .isTrue();
        assertThat(
                        AdAccountAssetService.class
                                .getMethod("importAccounts", List.class)
                                .isAnnotationPresent(Transactional.class))
                .isTrue();
        assertThat(
                        AdAccountAssetService.class
                                .getMethod(
                                        "syncPlatformAsset",
                                        AdAccountAssetModels.AdAccountAsset.class)
                                .isAnnotationPresent(Transactional.class))
                .isTrue();
        assertThat(
                        AdAccountAssetService.class
                                .getMethod(
                                        "syncFeishuAsset",
                                        AdAccountAssetModels.AdAccountAsset.class)
                                .isAnnotationPresent(Transactional.class))
                .isTrue();
    }

    private Account account(
            String cardNumber, String channelId, String channelName, List<Assignment> assignments) {
        return new Account(
                "act-1",
                "账户一",
                1,
                null,
                "AVAILABLE",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                cardNumber,
                "",
                "",
                "",
                "",
                null,
                channelId,
                channelName,
                true,
                "MANUAL_LOCKED",
                null,
                assignments);
    }
}
