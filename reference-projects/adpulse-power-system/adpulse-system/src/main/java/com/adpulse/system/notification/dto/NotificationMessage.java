package com.adpulse.system.notification.dto;

/** 站内通知与飞书通知共用的业务消息内容。 */
public record NotificationMessage(
        String title, String content, String targetPath, String businessType, Long businessId) {}
