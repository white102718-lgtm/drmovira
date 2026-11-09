package com.adpulse.system.notification.service;

import com.adpulse.system.notification.dto.SiteNotificationEnvelope;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/** 通过 Redis 广播已提交的站内通知，使任意 system 实例都能向本机 SSE 连接投递。 */
@Component
public class SiteNotificationEventBroker {
    public static final String CHANNEL = "adpulse:site-notification:events";

    private static final Logger LOGGER = LoggerFactory.getLogger(SiteNotificationEventBroker.class);

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;

    public SiteNotificationEventBroker(
            StringRedisTemplate redisTemplate, ObjectMapper objectMapper) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }

    /** 广播单条站内通知；数据库记录仍是断线补偿的最终事实来源。 */
    public void publish(SiteNotificationEnvelope envelope) {
        try {
            redisTemplate.convertAndSend(CHANNEL, objectMapper.writeValueAsString(envelope));
        } catch (JsonProcessingException exception) {
            LOGGER.error("站内通知事件序列化失败，notificationId={}", envelope.notification().id(), exception);
        } catch (RuntimeException exception) {
            LOGGER.error("站内通知事件广播失败，notificationId={}", envelope.notification().id(), exception);
        }
    }
}
