package com.adpulse.main.migration;

import java.util.HashSet;
import java.util.Set;
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** 默认关闭；来源凭据和操作员白名单只能由服务端配置，不能由 HTTP 请求指定。 */
@Getter
@Setter
@ConfigurationProperties("adpulse.asset-migration")
public class AssetMigrationProperties {
    private boolean enabled;
    private String sourceUrl;
    private String sourceUsername;
    private String sourcePassword;
    private String sourceUuid = "668439ab-d5b1-11f0-a11e-5635bb0443e0";
    private String sourceSchema = "fbad-suger";
    private TargetEnvironment targetEnvironment;
    private String targetUuid;
    private String targetSchema = "adpulse_system";
    private Set<Long> operatorIds = new HashSet<>();
    private boolean mappingCacheEnabled = true;

    /** 来源配置缺失时直接指出配置项，不把账号密码或连接串写入错误信息。 */
    public void validateSource() {
        AssetMigrationService.require(
                sourceUrl != null && !sourceUrl.isBlank(),
                "未配置来源数据库：请填写 adpulse.asset-migration.source-url 或 ASSET_MIGRATION_SOURCE_URL");
        AssetMigrationService.require(
                sourceUrl.startsWith("jdbc:mysql://"), "来源 source-url 格式错误：应以 jdbc:mysql:// 开头");
        AssetMigrationService.require(
                sourceUsername != null && !sourceUsername.isBlank(),
                "未配置来源用户名：请填写 source-username 或 ASSET_MIGRATION_SOURCE_USERNAME");
        AssetMigrationService.require(
                sourcePassword != null && !sourcePassword.isBlank(),
                "未配置来源密码：请填写 source-password 或 ASSET_MIGRATION_SOURCE_PASSWORD");
    }

    /** 账本表名只能由固定环境枚举选择，禁止拼接配置或 HTTP 输入作为 SQL 标识符。 */
    public enum TargetEnvironment {
        TEST,
        PRODUCTION
    }

    /** 每个环境使用自己的渠道迁移批次，不能复用另一个环境的主键映射。 */
    public String channelBatchKey() {
        validateEnvironment();
        return targetEnvironment == TargetEnvironment.TEST
                ? "mpower-prod-to-test-channels-v1"
                : "mpower-prod-to-prod-channels-v1";
    }

    /** 返回固定白名单中的账本名称，仅用于环境展示。 */
    public String channelLedgerTable() {
        validateEnvironment();
        return targetEnvironment == TargetEnvironment.TEST
                ? "mig_channel_prod_test_batch"
                : "mig_channel_prod_prod_batch";
    }

    /** 必须显式选择环境和实例，不再默认指向生产；已知生产实例不能标成测试。 */
    public void validateEnvironment() {
        AssetMigrationService.require(targetEnvironment != null, "必须配置迁移目标环境 TEST 或 PRODUCTION");
        AssetMigrationService.require(
                targetUuid != null
                        && !targetUuid.isBlank()
                        && targetSchema != null
                        && !targetSchema.isBlank()
                        && sourceUuid != null
                        && !sourceUuid.isBlank()
                        && sourceSchema != null
                        && !sourceSchema.isBlank(),
                "必须配置来源和目标实例 UUID 及库名");
        AssetMigrationService.require(
                !(targetEnvironment == TargetEnvironment.TEST
                                && "17c4f6b3-a2cc-11f1-99a8-ea697aa9ac3a".equals(targetUuid))
                        && !(targetEnvironment == TargetEnvironment.PRODUCTION
                                && "16903961-99f2-11f1-a1fe-86f52840e8b4".equals(targetUuid)),
                "目标环境与已知实例不符");
    }
}
