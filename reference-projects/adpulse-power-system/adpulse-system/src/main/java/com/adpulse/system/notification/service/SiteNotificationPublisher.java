package com.adpulse.system.notification.service;

import com.adpulse.system.notification.dto.NotificationMessage;
import com.adpulse.system.notification.dto.SiteNotificationEnvelope;
import com.adpulse.system.notification.dto.SiteNotificationEvent;
import com.adpulse.system.notification.mapper.SystemNotificationMapper;
import com.adpulse.system.notification.model.SiteNotificationRecord;
import java.time.LocalDateTime;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** 统一持久化站内通知，并在事务提交成功后广播 SSE 事件。 */
@Service
public class SiteNotificationPublisher {
    private final SystemNotificationMapper mapper;
    private final SiteNotificationEventBroker eventBroker;

    public SiteNotificationPublisher(
            SystemNotificationMapper mapper, SiteNotificationEventBroker eventBroker) {
        this.mapper = mapper;
        this.eventBroker = eventBroker;
    }

    /** 写入一名用户的站内通知。 */
    public void publish(Long userId, NotificationMessage message) {
        SiteNotificationRecord record = new SiteNotificationRecord();
        record.setUserId(userId);
        record.setTitle(message.title());
        record.setContent(message.content());
        record.setTargetPath(message.targetPath());
        record.setBusinessType(message.businessType());
        record.setBusinessId(message.businessId());
        record.setCreatedAt(LocalDateTime.now());
        mapper.insertNotification(record);

        SiteNotificationEnvelope envelope =
                new SiteNotificationEnvelope(userId, SiteNotificationEvent.from(record));
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            eventBroker.publish(envelope);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        eventBroker.publish(envelope);
                    }
                });
    }
}
