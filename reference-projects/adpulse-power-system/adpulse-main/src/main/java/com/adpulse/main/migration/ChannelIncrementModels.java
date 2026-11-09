package com.adpulse.main.migration;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/** 渠道增量迁移的来源快照、预检结果与执行请求。 */
public final class ChannelIncrementModels {
    private ChannelIncrementModels() {}

    /** 同一来源只读事务中的渠道与费率。 */
    public record SourceSnapshot(List<LegacyChannel> channels, List<LegacyRate> rates) {}

    public record LegacyChannel(
            long sourceId,
            String channelName,
            String channelShortName,
            String channelCode,
            int channelType,
            String belongTeam,
            int status,
            String settlementMethod,
            String settlementCurrency,
            BigDecimal buyoutAmount,
            String paymentAddress,
            String loginUrl,
            String remark,
            String tgGroupId,
            String tgGroupName,
            long tenantId,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {}

    public record LegacyRate(
            long sourceId,
            long sourceChannelId,
            BigDecimal serviceFee,
            BigDecimal rebateRate,
            LocalDate effectiveDate,
            LocalDate expiryDate,
            Integer status,
            BigDecimal damageRate,
            BigDecimal openingFee,
            String openingFeeUnit,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {}

    public record Candidate(
            String sourceId,
            String channelName,
            String channelCode,
            int rateCount,
            String action,
            String conflict) {}

    public record Plan(
            String environment,
            String planHash,
            int sourceCount,
            int mappedCount,
            int missingCount,
            List<Candidate> items) {}

    public record PlanRequest(List<String> sourceIds) {}

    public record ExecuteRequest(List<String> sourceIds, String planHash, boolean confirmed) {}

    public record ExecuteResult(
            String batchKey, String environment, int channelCount, int rateCount) {}

    public record ExistingMapping(long sourceId, long targetId) {}

    public record TargetConflict(long id, String channelName, String channelCode) {}

    /** 供 MyBatis 获取新渠道主键，并作为批次明细写入对象。 */
    public static class AppliedChannel {
        private final LegacyChannel source;
        private long targetId;

        public AppliedChannel(LegacyChannel source) {
            this.source = source;
        }

        public LegacyChannel getSource() {
            return source;
        }

        public long getTargetId() {
            return targetId;
        }

        public void setTargetId(long targetId) {
            this.targetId = targetId;
        }
    }
}
