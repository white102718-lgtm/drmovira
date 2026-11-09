package com.adpulse.system.notification.service;

import com.adpulse.system.notification.dto.SiteNotificationEnvelope;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

/** 将 Redis 广播转交给本实例持有的 SSE 连接。 */
@Component
public class SiteNotificationRedisSubscriber implements MessageListener {
    private static final Logger LOGGER =
            LoggerFactory.getLogger(SiteNotificationRedisSubscriber.class);

    private final ObjectMapper objectMapper;
    private final SiteNotificationStreamService streamService;

    public SiteNotificationRedisSubscriber(
            ObjectMapper objectMapper, SiteNotificationStreamService streamService) {
        this.objectMapper = objectMapper;
        this.streamService = streamService;
    }

    @Override
    public void onMessage(Message message, byte[] pattern) {
        try {
            SiteNotificationEnvelope envelope =
                    objectMapper.readValue(
                            new String(message.getBody(), StandardCharsets.UTF_8),
                            SiteNotificationEnvelope.class);
            streamService.deliver(envelope.userId(), envelope.notification());
        } catch (JsonProcessingException exception) {
            LOGGER.warn("忽略无法解析的站内通知 Redis 事件", exception);
        }
    }
}
