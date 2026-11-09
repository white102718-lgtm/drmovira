package com.adpulse.system.asset.service;

import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.mapper.AssetMapper;
import com.adpulse.system.asset.model.SiteNotification;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import java.util.List;
import org.springframework.stereotype.Service;

/** 站内通知查询与已读状态管理。 */
@Service
public class SiteNotificationService {
    private static final int MAX_PAGE_SIZE = 100;

    private final AssetMapper mapper;

    public SiteNotificationService(AssetMapper mapper) {
        this.mapper = mapper;
    }

    /** 返回当前用户是否存在未读通知，不加载通知正文。 */
    public AssetViews.NotificationUnreadStatus unreadStatus() {
        return new AssetViews.NotificationUnreadStatus(
                mapper.hasUnreadNotification(SecurityContextHelper.currentUserId()));
    }

    /** 按时间倒序返回当前用户的站内通知。 */
    public AssetViews.NotificationPage notifications(int page, int pageSize) {
        if (page < 1) throw BusinessException.validation("页码必须大于等于1");
        if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
            throw BusinessException.validation("每页条数必须在1到100之间");
        }

        long userId = SecurityContextHelper.currentUserId();
        int offset;
        try {
            offset = Math.multiplyExact(page - 1, pageSize);
        } catch (ArithmeticException exception) {
            throw BusinessException.validation("页码超出允许范围");
        }
        long total = mapper.countNotifications(userId);
        List<AssetViews.NotificationView> items =
                mapper.findNotifications(userId, offset, pageSize).stream()
                        .map(this::toView)
                        .toList();
        boolean hasMore = (long) offset + items.size() < total;
        return new AssetViews.NotificationPage(items, total, page, pageSize, hasMore);
    }

    /** 标记当前用户的单条通知为已读。 */
    public void markRead(Long id) {
        mapper.markNotificationRead(id, SecurityContextHelper.currentUserId());
    }

    /** 标记当前用户的全部通知为已读。 */
    public void markAllRead() {
        mapper.markAllNotificationsRead(SecurityContextHelper.currentUserId());
    }

    private AssetViews.NotificationView toView(SiteNotification notification) {
        return new AssetViews.NotificationView(
                notification.getId().toString(),
                notification.getTitle(),
                notification.getContent(),
                notification.getTargetPath(),
                notification.getBusinessType(),
                notification.getBusinessId() == null
                        ? null
                        : notification.getBusinessId().toString(),
                Boolean.TRUE.equals(notification.getRead()),
                notification.getCreatedAt());
    }
}
