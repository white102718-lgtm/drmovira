package com.adpulse.main.alertnotification.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import java.time.LocalDateTime;

/** 预警通知持久化模型。 */
public final class AlertModels {
    private AlertModels() {}

    public static class Config {
        public Long id;
        public Boolean enabled;
        public Boolean banEnabled;
        public Integer banThreshold;
        public Integer banWindowValue;
        public String banWindowUnit;
        public Boolean limitChangeEnabled;
        public Integer limitPollIntervalMinutes;
        @JsonIgnore public LocalDateTime limitChangeEnabledAt;
        public LocalDateTime updatedAt;
    }

    public static class Recipient {
        public Long id;
        public String recipientType;
        public String recipientKey;
        public String recipientName;
    }
}
