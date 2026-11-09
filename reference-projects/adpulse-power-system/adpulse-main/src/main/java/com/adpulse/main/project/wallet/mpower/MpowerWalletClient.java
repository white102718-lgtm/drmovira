package com.adpulse.main.project.wallet.mpower;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/** 使用现有开放接口HMAC协议调用旧MPower项目钱包聚合接口。 */
@Component
public class MpowerWalletClient {
    private static final String PATH = "/open/adpulse/project-wallet/ensure";
    private final MpowerWalletProperties properties;

    public MpowerWalletClient(MpowerWalletProperties properties) {
        this.properties = properties;
    }

    /** 查找或创建旧项目钱包，并同步返回展示地址。 */
    public WalletData ensureProjectWallet(EnsureWalletRequest request) {
        properties.validate();
        String timestamp = Long.toString(System.currentTimeMillis());
        String nonce = UUID.randomUUID().toString();
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(properties.getConnectTimeout());
        requestFactory.setReadTimeout(properties.getReadTimeout());
        RestClient client =
                RestClient.builder()
                        .baseUrl(properties.getBaseUrl())
                        .requestFactory(requestFactory)
                        .build();
        try {
            WalletEnvelope response =
                    client.post()
                            .uri(PATH)
                            .header("X-Timestamp", timestamp)
                            .header("X-Nonce", nonce)
                            .header("X-Sign", sign(timestamp + nonce))
                            .contentType(MediaType.APPLICATION_JSON)
                            .body(request)
                            .retrieve()
                            .body(WalletEnvelope.class);
            if (response == null || response.code() != 200 || response.data() == null) {
                throw new MpowerWalletClientException(
                        response == null || blank(response.msg())
                                ? "旧MPower钱包接口无有效响应"
                                : response.msg());
            }
            return response.data();
        } catch (RestClientException exception) {
            throw new MpowerWalletClientException("旧MPower钱包接口调用失败，请稍后重试", exception);
        }
    }

    private String sign(String content) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(
                    new SecretKeySpec(
                            properties.getSecret().getBytes(StandardCharsets.UTF_8),
                            "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(content.getBytes(StandardCharsets.UTF_8)));
        } catch (GeneralSecurityException exception) {
            throw new MpowerWalletClientException("旧MPower接口签名生成失败", exception);
        }
    }

    private boolean blank(String value) {
        return value == null || value.isBlank();
    }

    /** 旧系统项目创建参数；ID字段均按字符串传递，避免大整数精度损失。 */
    public record EnsureWalletRequest(
            String requestId,
            String sourceProjectCode,
            String projectName,
            Integer tenantId,
            String liabilityCompany,
            String region,
            Long taskStatus,
            String am,
            String dataSpecialist) {}

    /** 旧系统统一响应。 */
    public record WalletEnvelope(int code, String msg, WalletData data) {}

    /** 旧系统返回的项目钱包快照。 */
    public record WalletData(
            String legacyProjectId,
            String legacyProjectName,
            String accountKey,
            String accountName,
            String customerRefId,
            String teamId,
            List<CoinData> coins) {}

    /** 旧系统返回的单币种展示地址。 */
    public record CoinData(String coinKey, String coinName, String feeUnit, String address) {}

    /** 旧MPower钱包接口异常，不包含请求密钥或完整响应。 */
    public static class MpowerWalletClientException extends RuntimeException {
        public MpowerWalletClientException(String message) {
            super(message);
        }

        public MpowerWalletClientException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
