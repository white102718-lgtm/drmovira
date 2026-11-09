package com.adpulse.system.user.service;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.notification.dto.NotificationMessage;
import com.adpulse.system.notification.dto.NotificationRecipients;
import com.adpulse.system.notification.service.SystemNotificationService;
import com.adpulse.system.user.mapper.UserMapper;
import com.adpulse.system.user.model.UserAccount;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class UserDepartureFeishuNotifierTest {
    @Mock private UserMapper userMapper;
    @Mock private SystemNotificationService notificationService;

    @Test
    void sendsDepartureNoticeToAllOtherActiveMediaRoleMembers() {
        UserDepartureFeishuNotifier notifier =
                new UserDepartureFeishuNotifier(userMapper, notificationService, "媒介");
        UserAccount user = new UserAccount();
        user.setId(9L);
        user.setDisplayName("测试用户");
        when(userMapper.findActiveUserIdsByRoleName("媒介")).thenReturn(List.of(7L, 8L, 9L));

        notifier.notify(user, "停用");

        verify(notificationService)
                .notify(
                        eq(
                                new NotificationMessage(
                                        "人员离职通知",
                                        "用户“测试用户”已停用，其名下专属资产已释放为可分配状态，共享资产关系已移除。",
                                        "/system-management/users",
                                        "USER_DEPARTURE",
                                        9L)),
                        eq(NotificationRecipients.users(List.of(7L, 8L))));
    }
}
