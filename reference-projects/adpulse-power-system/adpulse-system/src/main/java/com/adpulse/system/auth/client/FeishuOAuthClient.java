package com.adpulse.system.auth.client;

import com.adpulse.system.auth.model.FeishuIdentity;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.FeishuApplicationConfig;
import com.adpulse.system.feishuorg.security.FeishuSecretCipher;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/** 飞书旧版网页 OAuth 客户端，与二维码 SDK 支持的授权流程保持一致。 */
@Component
public class FeishuOAuthClient {

    private final FeishuOrganizationMapper mapper;
    private final FeishuSecretCipher cipher;
    private final RestClient client;

    @Autowired
    public FeishuOAuthClient(FeishuOrganizationMapper mapper, FeishuSecretCipher cipher) {
        this(mapper, cipher, RestClient.builder());
    }

    FeishuOAuthClient(
            FeishuOrganizationMapper mapper,
            FeishuSecretCipher cipher,
            RestClient.Builder clientBuilder) {
        this.mapper = mapper;
        this.cipher = cipher;
        this.client = clientBuilder.baseUrl("https://open.feishu.cn/open-apis").build();
    }

    /** 返回已配置的飞书应用 ID。 */
    public String applicationId() {
        return requireConfiguration().getAppId();
    }

    /** 使用一次性授权码换取当前飞书用户身份。 */
    public FeishuIdentity exchangeCode(String code) {
        try {
            return exchangeCodeInternal(code);
        } catch (RestClientException exception) {
            throw BusinessException.conflict("飞书登录服务暂不可用，请稍后重试");
        }
    }

    private FeishuIdentity exchangeCodeInternal(String code) {
        FeishuApplicationConfig configuration = requireConfiguration();
        String appSecret = cipher.decrypt(configuration.getAppSecretCiphertext());
        String appAccessToken = appAccessToken(configuration.getAppId(), appSecret);
        Map<?, ?> response =
                client.post()
                        .uri("/authen/v1/access_token")
                        .header("Authorization", "Bearer " + appAccessToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("grant_type", "authorization_code", "code", code))
                        .retrieve()
                        .body(Map.class);
        requireSuccess(response, "飞书授权码无效或已过期，请重新扫码");
        Map<?, ?> data = map(response == null ? null : response.get("data"));
        String tenantKey = text(data == null ? null : data.get("tenant_key"));
        String openId = text(data == null ? null : data.get("open_id"));
        String unionId = text(data == null ? null : data.get("union_id"));
        String displayName = text(data == null ? null : data.get("name"));
        if (!StringUtils.hasText(tenantKey) || !StringUtils.hasText(openId)) {
            throw authenticationFailure("飞书未返回完整的用户身份，请重新扫码");
        }
        return new FeishuIdentity(
                tenantKey, openId, blankToNull(unionId), blankToNull(displayName));
    }

    private String appAccessToken(String appId, String appSecret) {
        Map<?, ?> response =
                client.post()
                        .uri("/auth/v3/app_access_token/internal")
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("app_id", appId, "app_secret", appSecret))
                        .retrieve()
                        .body(Map.class);
        requireSuccess(response, "飞书应用鉴权失败，请联系管理员检查应用配置");
        String token = text(response == null ? null : response.get("app_access_token"));
        if (!StringUtils.hasText(token)) {
            throw BusinessException.conflict("飞书未返回应用访问令牌");
        }
        return token;
    }

    private FeishuApplicationConfig requireConfiguration() {
        FeishuApplicationConfig configuration = mapper.findApplicationConfig();
        if (configuration == null
                || !StringUtils.hasText(configuration.getAppId())
                || !StringUtils.hasText(configuration.getAppSecretCiphertext())) {
            throw BusinessException.conflict("请先配置飞书应用");
        }
        return configuration;
    }

    private void requireSuccess(Map<?, ?> response, String message) {
        if (response == null || !"0".equals(text(response.get("code")))) {
            throw authenticationFailure(message);
        }
    }

    private BusinessException authenticationFailure(String message) {
        return new BusinessException(ApiCode.AUTHENTICATION_FAILED, message);
    }

    private Map<?, ?> map(Object value) {
        return value instanceof Map<?, ?> result ? result : null;
    }

    private String text(Object value) {
        return value == null ? "" : value.toString();
    }

    private String blankToNull(String value) {
        return StringUtils.hasText(value) ? value : null;
    }
}
