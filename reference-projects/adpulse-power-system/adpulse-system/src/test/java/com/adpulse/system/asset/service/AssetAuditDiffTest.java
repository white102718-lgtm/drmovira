package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import com.adpulse.system.asset.mapper.AssetMapper;
import com.adpulse.system.auth.service.MfaSecretCipher;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.Transactional;

class AssetAuditDiffTest {
    private final AssetService service =
            new AssetService(
                    mock(AssetMapper.class),
                    mock(AssetExcelCodec.class),
                    mock(MfaSecretCipher.class));

    @Test
    void recordsClearButIgnoresNoOp() {
        var before = snapshot("备注", Map.of("displayName", "账号甲"));
        var after = snapshot(null, Map.of("displayName", "账号甲"));

        var changes = service.auditChanges(before, after);

        assertThat(changes).hasSize(1);
        assertThat(changes.getFirst().fieldKey()).isEqualTo("remark");
        assertThat(changes.getFirst().after().display()).isNull();
        assertThat(service.auditChanges(before, before)).isEmpty();
    }

    @Test
    void neverStoresSensitiveCredentialPlaintext() {
        var before = snapshot(null, Map.of("password", "old-secret", "cookie", "cookie-a"));
        var after = snapshot(null, Map.of("password", "new-secret", "cookie", ""));

        var changes = service.auditChanges(before, after);

        assertThat(changes).extracting("fieldKey").containsExactly("cookie", "password");
        assertThat(changes)
                .allSatisfy(
                        change -> {
                            assertThat(change.before().redacted()).isTrue();
                            assertThat(change.after().redacted()).isTrue();
                            assertThat(change.toString())
                                    .doesNotContain("old-secret", "new-secret", "cookie-a");
                        });
        assertThat(
                        changes.stream()
                                .filter(change -> change.fieldKey().equals("password"))
                                .findFirst()
                                .orElseThrow()
                                .after()
                                .display())
                .isEqualTo("已重新设置");
    }

    @Test
    void optionValueKeepsCodeAndNameSnapshot() {
        var changes =
                service.auditChanges(
                        snapshot(null, Map.of("gender", "male")),
                        snapshot(null, Map.of("gender", "female")));

        var gender = changes.getFirst();
        assertThat(gender.before().display()).isEqualTo("男");
        assertThat(gender.before().references().getFirst().id()).isEqualTo("male");
        assertThat(gender.after().display()).isEqualTo("女");
        assertThat(gender.after().references().getFirst().id()).isEqualTo("female");
    }

    @Test
    void initialSnapshotKeepsNonEmptyFieldsAndRedactsCredentials() {
        var snapshot =
                new AssetService.AssetAuditSnapshot(
                        "PERSONAL",
                        "账号一",
                        "code-1",
                        "10",
                        "渠道一",
                        "20",
                        "项目一",
                        "团队一",
                        "ASSIGNED",
                        30L,
                        "用户一",
                        "30,31",
                        "用户一、用户二",
                        null,
                        new LinkedHashMap<>(
                                Map.of(
                                        "inventorySubtype", "fb",
                                        "password", "plain-secret")));

        var changes = service.initialChanges(snapshot);

        assertThat(changes)
                .extracting("fieldKey")
                .contains("assetType", "assetSubtype", "usageUsers", "password")
                .doesNotContain("remark");
        var password =
                changes.stream()
                        .filter(change -> change.fieldKey().equals("password"))
                        .findFirst()
                        .orElseThrow();
        assertThat(password.after().display()).isEqualTo("已设置");
        assertThat(password.toString()).doesNotContain("plain-secret");
    }

    @Test
    void updateEntrypointsRemainTransactionalForRollback() throws Exception {
        assertThat(
                        AssetService.class
                                .getMethod(
                                        "updateAsset",
                                        Long.class,
                                        com.adpulse.system.asset.dto.AssetRequests.AssetSave.class)
                                .isAnnotationPresent(Transactional.class))
                .isTrue();
        assertThat(
                        AssetService.class
                                .getMethod(
                                        "batchUpdateAssets",
                                        com.adpulse.system.asset.dto.AssetRequests.AssetBatchUpdate
                                                .class)
                                .isAnnotationPresent(Transactional.class))
                .isTrue();
        assertThat(
                        AssetService.class
                                .getMethod(
                                        "spreadsheetSave",
                                        com.adpulse.system.asset.dto.AssetRequests
                                                .AssetSpreadsheetSave.class)
                                .isAnnotationPresent(Transactional.class))
                .isTrue();
        assertThat(
                        AssetService.class
                                .getMethod(
                                        "registerOpenedAdAccounts",
                                        String.class,
                                        String.class,
                                        String.class,
                                        String.class,
                                        long.class,
                                        long.class,
                                        String.class,
                                        long.class)
                                .isAnnotationPresent(Transactional.class))
                .isTrue();
    }

    private AssetService.AssetAuditSnapshot snapshot(String remark, Map<String, String> details) {
        return new AssetService.AssetAuditSnapshot(
                "PERSONAL",
                "资产一",
                "code-1",
                "10",
                "渠道甲",
                "20",
                "项目甲",
                "团队甲",
                "AVAILABLE",
                null,
                null,
                null,
                null,
                remark,
                new LinkedHashMap<>(details));
    }
}
