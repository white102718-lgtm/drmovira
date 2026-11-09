package com.adpulse.system.feishuorg.service;

import com.adpulse.system.feishuorg.model.FeishuApplicationConfig;
import com.adpulse.system.feishuorg.security.FeishuSecretCipher;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;

/**
 * 基于已配置的飞书自建应用向系统用户发送私聊消息。
 *
 * <p>仅向已启用且已同步飞书 open_id 的用户投递；飞书配置或网络异常只记录告警，不能影响业务事务。
 */
@Component
public class FeishuMessageNotifier {
    private static final Logger log = LoggerFactory.getLogger(FeishuMessageNotifier.class);

    private final FeishuNotificationRecipientResolver recipientResolver;
    private final FeishuSecretCipher cipher;
    private final ObjectMapper json;
    private final RestClient client;

    public FeishuMessageNotifier(
            FeishuNotificationRecipientResolver recipientResolver,
            FeishuSecretCipher cipher,
            ObjectMapper json) {
        this.recipientResolver = recipientResolver;
        this.cipher = cipher;
        this.json = json;
        this.client = RestClient.builder().baseUrl("https://open.feishu.cn/open-apis").build();
    }

    /**
     * 向指定系统用户发送飞书文本消息。
     *
     * <p>用户未绑定飞书或飞书应用未配置时自动跳过，不抛出业务异常。
     */
    public void notifyUsers(List<Long> userIds, String content) {
        if (userIds == null || userIds.isEmpty() || !StringUtils.hasText(content)) return;

        try {
            List<String> openIds = recipientResolver.resolveOpenIds(userIds);
            if (openIds.isEmpty()) {
                log.warn("Feishu notification skipped: no active recipient with a Feishu open_id");
                return;
            }

            FeishuApplicationConfig configuration = recipientResolver.findApplicationConfig();
            if (configuration == null
                    || !StringUtils.hasText(configuration.getAppId())
                    || !StringUtils.hasText(configuration.getAppSecretCiphertext())) {
                log.warn("Feishu notification skipped: no configured Feishu application");
                return;
            }
            String tenantToken = tenantAccessToken(configuration);
            for (String openId : openIds) {
                sendText(tenantToken, openId, recipientResolver.decorateContent(content));
            }
            log.info("Feishu notification delivered to {} recipient(s)", openIds.size());
        } catch (RuntimeException exception) {
            log.warn("Feishu notification failed: {}", exception.getMessage());
        }
    }

    private String tenantAccessToken(FeishuApplicationConfig configuration) {
        Map<?, ?> response =
                client.post()
                        .uri("/auth/v3/tenant_access_token/internal")
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(
                                Map.of(
                                        "app_id", configuration.getAppId(),
                                        "app_secret",
                                                cipher.decrypt(
                                                        configuration.getAppSecretCiphertext())))
                        .retrieve()
                        .body(Map.class);
        if (response == null || !"0".equals(String.valueOf(response.get("code")))) {
            throw new IllegalStateException("Feishu tenant authentication was rejected");
        }
        String token = String.valueOf(response.get("tenant_access_token"));
        if (!StringUtils.hasText(token) || "null".equals(token)) {
            throw new IllegalStateException("Feishu did not return a tenant access token");
        }
        return token;
    }

    private void sendText(String tenantToken, String openId, String text) {
        Map<?, ?> response =
                client.post()
                        .uri("/im/v1/messages?receive_id_type=open_id")
                        .header("Authorization", "Bearer " + tenantToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(
                                Map.of(
                                        "receive_id",
                                        openId,
                                        "msg_type",
                                        "text",
                                        "content",
                                        textContent(text)))
                        .retrieve()
                        .body(Map.class);
        if (response == null || !"0".equals(String.valueOf(response.get("code")))) {
            throw new IllegalStateException("Feishu message delivery was rejected");
        }
    }

    private String textContent(String text) {
        try {
            return json.writeValueAsString(Map.of("text", text));
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Failed to encode Feishu text message", exception);
        }
    }
}
