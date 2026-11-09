package com.ruoyi.system.orbit.analysis;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.*;

/** 内部可信命中和持久化任务；不能作为未鉴权HTTP入队参数。 */
public final class AnalysisJobModels {
    private AnalysisJobModels() {}

    public record TrustedHit(
            String tenantId,
            String ruleId,
            long ruleRevision,
            String entityId,
            String hitId,
            String slot,
            String zone,
            String policyId,
            int ruleCooldown,
            int ruleDaily,
            JsonNode facts) {
        @Override
        public String toString() {
            return "TrustedHit[REDACTED]";
        }
    }

    public record Admission(String id, String state, long generation, String inputHash) {}

    public static final class Gate {
        public long generation;
        public Instant lastAdmittedAt;
    }

    public static final class Job {
        public String id,
                tenantId,
                ruleId,
                entityId,
                hitId,
                slot,
                zone,
                state,
                dedupeHash,
                inputHash,
                policyId,
                providerId;
        public long ruleRevision, generation, revision, policyRevision, providerRevision;
        public LocalDate businessDate;
        public Instant createdAt;
        @JsonIgnore public String inputJson;
        @JsonIgnore public String settingsJson;
    }
}
