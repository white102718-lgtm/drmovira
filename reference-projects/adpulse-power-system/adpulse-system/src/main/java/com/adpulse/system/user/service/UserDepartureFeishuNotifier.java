package com.adpulse.system.user.service;

import com.adpulse.system.notification.dto.NotificationMessage;
import com.adpulse.system.notification.dto.NotificationRecipients;
import com.adpulse.system.notification.service.SystemNotificationService;
import com.adpulse.system.user.mapper.UserMapper;
import com.adpulse.system.user.model.UserAccount;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

/** 人员离职完成后，通过统一通知服务告知媒介角色成员。 */
@Component
public class UserDepartureFeishuNotifier {
    private static final Logger log = LoggerFactory.getLogger(UserDepartureFeishuNotifier.class);

    private final UserMapper userMapper;
    private final SystemNotificationService notificationService;
    private final String notificationRoleName;

    public UserDepartureFeishuNotifier(
            UserMapper userMapper,
            SystemNotificationService notificationService,
            @Value("${adpulse.user.departure.notification-role-name:媒介}")
                    String notificationRoleName) {
        this.userMapper = userMapper;
        this.notificationService = notificationService;
        this.notificationRoleName =
                StringUtils.hasText(notificationRoleName) ? notificationRoleName.trim() : "媒介";
    }

    /** 向媒介角色下的所有启用成员写入站内通知，并在事务提交后同步投递飞书。 */
    public void notify(UserAccount user, String departureAction) {
        if (user == null) return;

        List<Long> recipientIds =
                userMapper.findActiveUserIdsByRoleName(notificationRoleName).stream()
                        .filter(recipientId -> !recipientId.equals(user.getId()))
                        .toList();
        if (recipientIds.isEmpty()) {
            log.warn(
                    "User departure notification skipped: no active member in role {}",
                    notificationRoleName);
            return;
        }
        notificationService.notify(
                new NotificationMessage(
                        "人员离职通知",
                        departureContent(user, departureAction),
                        "/system-management/users",
                        "USER_DEPARTURE",
                        user.getId()),
                NotificationRecipients.users(recipientIds));
    }

    private String departureContent(UserAccount user, String departureAction) {
        String userName =
                StringUtils.hasText(user.getDisplayName())
                        ? user.getDisplayName()
                        : "用户ID " + user.getId();
        return "用户“" + userName + "”已" + departureAction + "，其名下专属资产已释放为可分配状态，共享资产关系已移除。";
    }
}
