package com.adpulse.system.notification.dto;

import com.adpulse.system.notification.model.SiteNotificationRecord;
import java.time.LocalDateTime;

/** 推送给前端的站内通知事件；大整数 ID 始终序列化为字符串。 */
public record SiteNotificationEvent(
        String id,
        String title,
        String message,
        String targetPath,
        String businessType,
        String businessId,
        boolean isRead,
        LocalDateTime createdAt) {

    /** 将持久化记录转换成与通知列表一致的前端结构。 */
    public static SiteNotificationEvent from(SiteNotificationRecord record) {
        return new SiteNotificationEvent(
                record.getId().toString(),
                record.getTitle(),
                record.getContent(),
                record.getTargetPath(),
                record.getBusinessType(),
                record.getBusinessId() == null ? null : record.getBusinessId().toString(),
                false,
                record.getCreatedAt());
    }
}
