package com.adpulse.main.alertnotification.mapper;

import com.adpulse.main.alertnotification.dto.AlertRequests.ConfigSave;
import com.adpulse.main.alertnotification.dto.AlertRequests.RecipientSave;
import com.adpulse.main.alertnotification.model.AlertModels.Config;
import com.adpulse.main.alertnotification.model.AlertModels.Recipient;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface AlertNotificationMapper {
    Config findConfig();

    List<Recipient> findRecipients();

    String findActiveUserPhone(@Param("userId") Long userId);

    void updateConfig(
            @Param("request") ConfigSave request,
            @Param("limitPollIntervalMinutes") Integer limitPollIntervalMinutes,
            @Param("limitChangeEnabledAt") LocalDateTime limitChangeEnabledAt,
            @Param("updatedBy") Long updatedBy);

    void deleteRecipients();

    void insertRecipient(RecipientSave recipient);

    int insertNotification(
            @Param("alertType") String alertType,
            @Param("dedupeKey") String dedupeKey,
            @Param("title") String title,
            @Param("content") String content,
            @Param("accountId") String accountId,
            @Param("accountName") String accountName,
            @Param("triggerValue") BigDecimal triggerValue,
            @Param("thresholdValue") BigDecimal thresholdValue,
            @Param("currency") String currency,
            @Param("sourceEventId") String sourceEventId,
            @Param("occurredAt") LocalDateTime occurredAt);

    Long findNotificationIdByDedupeKey(@Param("dedupeKey") String dedupeKey);

    void insertDelivery(
            @Param("notificationId") Long notificationId,
            @Param("recipientType") String recipientType,
            @Param("recipientKey") String recipientKey,
            @Param("recipientName") String recipientName,
            @Param("deliveryStatus") String deliveryStatus,
            @Param("errorMessage") String errorMessage,
            @Param("deliveredAt") LocalDateTime deliveredAt);
}
