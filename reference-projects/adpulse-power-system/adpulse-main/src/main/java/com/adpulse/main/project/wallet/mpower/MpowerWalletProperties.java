package com.adpulse.main.project.wallet.mpower;

import java.time.Duration;
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** 临时旧MPower钱包适配配置；旧系统下线后可连同本包整体删除。 */
@Getter
@Setter
@ConfigurationProperties("adpulse.mpower-wallet")
public class MpowerWalletProperties {
    private String baseUrl;
    private String secret;
    private Duration connectTimeout = Duration.ofSeconds(3);
    private Duration readTimeout = Duration.ofSeconds(30);
    private String sourceUrl;
    private String sourceUsername;
    private String sourcePassword;
    private String sourceUuid = "668439ab-d5b1-11f0-a11e-5635bb0443e0";
    private String sourceSchema = "fbad-suger";
    private String mappingNamespace = "default";
    private boolean mappingCacheEnabled = true;
    private Duration mappingCacheTtl = Duration.ofHours(24);
    private Duration mappingFallbackCacheTtl = Duration.ofMinutes(30);
    private Integer defaultTenantId = 1;
    private String defaultDepartmentId = "100";
    private String defaultRegion = "美国";
    private String defaultUserId = "1";

    /** 调用旧系统前校验必要配置，不在异常中输出密钥。 */
    public void validate() {
        if (baseUrl == null || baseUrl.isBlank()) {
            throw new MpowerWalletClient.MpowerWalletClientException("未配置旧MPower钱包接口地址");
        }
        if (secret == null || secret.isBlank()) {
            throw new MpowerWalletClient.MpowerWalletClientException("未配置旧MPower钱包接口签名密钥");
        }
    }

    /** 查询老系统组织映射前校验复用的迁移数据源配置。 */
    public void validateSource() {
        if (sourceUrl == null || !sourceUrl.startsWith("jdbc:mysql://")) {
            throw new MpowerWalletClient.MpowerWalletClientException("未正确配置旧MPower来源数据库地址");
        }
        if (sourceUsername == null || sourceUsername.isBlank()) {
            throw new MpowerWalletClient.MpowerWalletClientException("未配置旧MPower来源数据库用户名");
        }
        if (sourcePassword == null || sourcePassword.isBlank()) {
            throw new MpowerWalletClient.MpowerWalletClientException("未配置旧MPower来源数据库密码");
        }
    }
}
