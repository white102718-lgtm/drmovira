package com.adpulse.system.notification.service;

import com.adpulse.system.feishuorg.service.MpowerFeishuNotifier;
import com.adpulse.system.notification.dto.NotificationMessage;
import com.adpulse.system.notification.dto.NotificationRecipients;
import com.adpulse.system.notification.mapper.SystemNotificationMapper;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.util.StringUtils;

/** 统一投递站内与飞书通知，并支持按人员、角色和部门选择收件人。 */
@Service
public class SystemNotificationService {
    private final SystemNotificationMapper mapper;
    private final SiteNotificationPublisher siteNotificationPublisher;
    private final MpowerFeishuNotifier mpowerFeishuNotifier;

    public SystemNotificationService(
            SystemNotificationMapper mapper,
            SiteNotificationPublisher siteNotificationPublisher,
            MpowerFeishuNotifier mpowerFeishuNotifier) {
        this.mapper = mapper;
        this.siteNotificationPublisher = siteNotificationPublisher;
        this.mpowerFeishuNotifier = mpowerFeishuNotifier;
    }

    /**
     * 写入站内通知，并在当前事务提交成功后发送飞书通知。
     *
     * <p>收件人选择器可组合使用；最终只会向仍启用的用户写入和投递一次。
     */
    public void notify(NotificationMessage message, NotificationRecipients recipients) {
        if (message == null
                || recipients == null
                || !StringUtils.hasText(message.title())
                || !StringUtils.hasText(message.content())) {
            return;
        }

        List<Long> recipientIds = resolveRecipientIds(recipients);
        if (recipientIds.isEmpty()) return;

        for (Long userId : recipientIds) {
            siteNotificationPublisher.publish(userId, message);
        }
        Runnable feishuDelivery =
                () ->
                        mpowerFeishuNotifier.notifyUsers(
                                recipientIds, message.title() + "\n" + message.content());
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            feishuDelivery.run();
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        feishuDelivery.run();
                    }
                });
    }

    private List<Long> resolveRecipientIds(NotificationRecipients recipients) {
        Set<Long> recipientIds = new LinkedHashSet<>();
        List<Long> userIds = validIds(recipients.userIds());
        List<Long> roleIds = validIds(recipients.roleIds());
        List<Long> departmentIds = validIds(recipients.departmentIds());
        if (!userIds.isEmpty()) addAll(recipientIds, mapper.findActiveUserIds(userIds));
        if (!roleIds.isEmpty()) addAll(recipientIds, mapper.findActiveUserIdsByRoles(roleIds));
        if (!departmentIds.isEmpty()) {
            addAll(recipientIds, mapper.findActiveUserIdsByDepartments(departmentIds));
        }
        return List.copyOf(recipientIds);
    }

    private List<Long> validIds(List<Long> ids) {
        return ids.stream().filter(id -> id != null && id > 0).distinct().toList();
    }

    private void addAll(Set<Long> target, List<Long> ids) {
        if (ids == null) return;
        ids.stream().filter(id -> id != null && id > 0).forEach(target::add);
    }
}
