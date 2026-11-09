package com.adpulse.system.notification.dto;

/** Redis 通知信封；userId 只用于服务端定向投递，不发送给浏览器。 */
public record SiteNotificationEnvelope(Long userId, SiteNotificationEvent notification) {}
