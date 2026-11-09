package com.adpulse.main.cloak.config;

import com.adpulse.main.cloak.client.GlobalPwaClient.GlobalPwaClientException;
import java.time.Duration;
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** GlobalPWA斗篷服务商接口配置。 */
@Getter
@Setter
@ConfigurationProperties("adpulse.global-pwa")
public class GlobalPwaProperties {
    private String baseUrl = "https://www.globalpwa.com/prod-api";
    private String apiToken;
    private Duration connectTimeout = Duration.ofSeconds(3);
    private Duration readTimeout = Duration.ofSeconds(15);

    /** 调用服务商接口前校验必要配置，异常中不包含Token。 */
    public void validate() {
        if (baseUrl == null || baseUrl.isBlank()) {
            throw new GlobalPwaClientException("未配置GlobalPWA接口地址");
        }
        if (apiToken == null || apiToken.isBlank()) {
            throw new GlobalPwaClientException("未配置GlobalPWA接口Token");
        }
    }
}
