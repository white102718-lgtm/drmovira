package com.adpulse.system.notification.service;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.feishuorg.service.MpowerFeishuNotifier;
import com.adpulse.system.notification.dto.NotificationMessage;
import com.adpulse.system.notification.dto.NotificationRecipients;
import com.adpulse.system.notification.mapper.SystemNotificationMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class SystemNotificationServiceTest {
    @Mock private SystemNotificationMapper mapper;
    @Mock private SiteNotificationPublisher siteNotificationPublisher;
    @Mock private MpowerFeishuNotifier mpowerFeishuNotifier;

    @Test
    void notifiesDeduplicatedActiveRecipientsFromUsersRolesAndDepartments() {
        SystemNotificationService service =
                new SystemNotificationService(
                        mapper, siteNotificationPublisher, mpowerFeishuNotifier);
        NotificationMessage message =
                new NotificationMessage(
                        "审批通知", "申请已驳回", "/workbench/approvals?id=8", "APPROVAL", 8L);
        NotificationRecipients recipients =
                new NotificationRecipients(List.of(1L, 1L), List.of(2L), List.of(3L));
        when(mapper.findActiveUserIds(List.of(1L))).thenReturn(List.of(1L));
        when(mapper.findActiveUserIdsByRoles(List.of(2L))).thenReturn(List.of(1L, 2L));
        when(mapper.findActiveUserIdsByDepartments(List.of(3L))).thenReturn(List.of(2L, 3L));

        service.notify(message, recipients);

        verify(siteNotificationPublisher).publish(1L, message);
        verify(siteNotificationPublisher).publish(2L, message);
        verify(siteNotificationPublisher).publish(3L, message);
        verify(mpowerFeishuNotifier).notifyUsers(List.of(1L, 2L, 3L), "审批通知\n申请已驳回");
    }
}
