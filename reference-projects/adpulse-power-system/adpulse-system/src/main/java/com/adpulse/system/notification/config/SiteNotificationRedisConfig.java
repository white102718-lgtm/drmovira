package com.adpulse.system.notification.config;

import com.adpulse.system.notification.service.SiteNotificationEventBroker;
import com.adpulse.system.notification.service.SiteNotificationRedisSubscriber;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

/** 站内通知跨实例广播订阅配置。 */
@Configuration
public class SiteNotificationRedisConfig {
    @Bean
    RedisMessageListenerContainer siteNotificationRedisListenerContainer(
            RedisConnectionFactory connectionFactory, SiteNotificationRedisSubscriber subscriber) {
        RedisMessageListenerContainer container = new RedisMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(
                subscriber, new ChannelTopic(SiteNotificationEventBroker.CHANNEL));
        return container;
    }
}
