package com.ruoyi.system.orbit.analysis;

import static com.ruoyi.system.orbit.analysis.AnalysisJobModels.*;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.ruoyi.system.orbit.config.*;
import com.ruoyi.system.orbit.config.ConfigurationModels.Row;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 内部可信命中入队事务。规则对象鉴权/命中持久化上游尚未接通，禁止直接增加HTTP入口。 */
@Service
public class AnalysisJobStore {
    private final AnalysisJobMapper mapper;
    private final AnalysisInputGuard guard;
    private final ObjectMapper json;
    private final Clock clock;

    @Autowired
    public AnalysisJobStore(AnalysisJobMapper mapper, AnalysisInputGuard guard, ObjectMapper json) {
        this(mapper, guard, json, Clock.systemUTC());
    }

    public AnalysisJobStore(
            AnalysisJobMapper mapper, AnalysisInputGuard guard, ObjectMapper json, Clock clock) {
        this.mapper = mapper;
        this.guard = guard;
        this.json = json.copy().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
        this.clock = clock;
    }

    /** 数据库队列同时承担持久化待办，不发送模型请求，也不生成占位建议。 */
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Admission admitTrustedHit(TrustedHit hit) {
        if (hit == null) throw invalid();
        for (String id :
                Arrays.asList(
                        hit.tenantId(),
                        hit.ruleId(),
                        hit.entityId(),
                        hit.hitId(),
                        hit.policyId())) {
            try {
                if (id == null || !UUID.fromString(id).toString().equalsIgnoreCase(id))
                    throw invalid();
            } catch (IllegalArgumentException error) {
                throw invalid();
            }
        }
        if (hit.ruleRevision() < 1
                || hit.facts() == null
                || !hit.entityId().equals(hit.facts().path("entity_id").asText())) throw invalid();
        ZoneId zone;
        try {
            zone = ZoneId.of(hit.zone());
        } catch (Exception error) {
            throw invalid();
        }
        String slot = ConfigurationCatalog.normalizeText(hit.slot(), 100, "调度slot");
        Row policy = mapper.configurationShared(hit.tenantId(), hit.policyId());
        if (policy == null || !policy.enabled || !"AI_SUGGESTIONS".equals(policy.section))
            throw unavailable();
        Map<String, Object> policySettings =
                ConfigurationCatalog.validate(
                        "AI_SUGGESTIONS", settings(policy.settingsJson), true);
        Row provider =
                mapper.configurationShared(
                        hit.tenantId(), policySettings.get("providerConfigId").toString());
        if (provider == null
                || !provider.enabled
                || !Set.of("AI_GPT", "AI_CLAUDE").contains(provider.section)
                || !"READ_VERIFIED".equals(provider.verificationStatus)) throw unavailable();
        Map<String, Object> providerSettings =
                ConfigurationCatalog.validate(
                        provider.section, settings(provider.settingsJson), true);
        ObjectNode facts = hit.facts().deepCopy();
        facts.put("policy_version", policy.id + ":" + policy.revision);
        var frozen =
                guard.prepare(
                        facts,
                        hit.tenantId(),
                        policySettings,
                        (Integer) providerSettings.get("maxOutputTokens"),
                        hit.ruleCooldown(),
                        hit.ruleDaily());
        Job job = new Job();
        job.id = UUID.randomUUID().toString();
        job.tenantId = hit.tenantId();
        job.ruleId = hit.ruleId();
        job.ruleRevision = hit.ruleRevision();
        job.entityId = hit.entityId();
        job.hitId = hit.hitId();
        job.slot = slot;
        job.zone = zone.getId();
        job.createdAt = clock.instant();
        job.businessDate = job.createdAt.atZone(zone).toLocalDate();
        job.policyId = policy.id;
        job.policyRevision = policy.revision;
        job.providerId = provider.id;
        job.providerRevision = provider.revision;
        job.inputJson = frozen.json();
        job.inputHash = frozen.sha256();
        job.state = "QUEUED";
        job.settingsJson =
                encode(
                        Map.of(
                                "policy",
                                policySettings,
                                "provider",
                                providerSettings,
                                "effective",
                                Map.of(
                                        "cooldownMinutes",
                                        frozen.cooldownMinutes(),
                                        "maximumDailyAnalysesPerObject",
                                        frozen.maximumDailyAnalysesPerObject(),
                                        "maxOutputTokens",
                                        frozen.maxOutputTokens())));
        job.dedupeHash =
                hash(
                        encode(
                                List.of(
                                        hit.tenantId(),
                                        hit.hitId(),
                                        job.inputHash,
                                        provider.id,
                                        provider.revision,
                                        policy.id,
                                        policy.revision)));
        mapper.reserveGate(job.tenantId, job.ruleId, job.entityId);
        Gate gate = mapper.gate(job.tenantId, job.ruleId, job.entityId);
        Job replay = mapper.replay(job.tenantId, job.dedupeHash);
        if (replay != null) {
            if (!hit.ruleId().equals(replay.ruleId)
                    || hit.ruleRevision() != replay.ruleRevision
                    || !slot.equals(replay.slot))
                throw new ConfigurationException(
                        409, "ANALYSIS_HIT_REBOUND", "命中身份不可改绑规则版本或调度slot");
            return admission(replay);
        }
        if (gate.lastAdmittedAt != null
                && job.createdAt.isBefore(
                        gate.lastAdmittedAt.plusSeconds(frozen.cooldownMinutes() * 60L)))
            throw new ConfigurationException(429, "ANALYSIS_COOLDOWN", "分析对象仍处于冷却期");
        mapper.reserveQuota(job);
        if (mapper.quota(job) >= frozen.maximumDailyAnalysesPerObject()
                || mapper.consumeQuota(job, frozen.maximumDailyAnalysesPerObject()) != 1)
            throw new ConfigurationException(429, "ANALYSIS_DAILY_LIMIT", "规则对象当地日分析次数已达上限");
        job.generation = Math.addExact(gate.generation, 1);
        mapper.insert(job);
        mapper.supersedeEvents(job);
        mapper.supersede(job);
        mapper.queuedEvent(job);
        if (mapper.advanceGate(job) != 1)
            throw new ConfigurationException(409, "ANALYSIS_GENERATION_CONFLICT", "分析代次已变化");
        return admission(job);
    }

    private Admission admission(Job job) {
        return new Admission(job.id, job.state, job.generation, job.inputHash);
    }

    private Map<String, Object> settings(String value) {
        try {
            return json.readValue(value, new TypeReference<Map<String, Object>>() {});
        } catch (Exception error) {
            throw invalid();
        }
    }

    private String encode(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (Exception error) {
            throw invalid();
        }
    }

    private String hash(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw invalid();
        }
    }

    private ConfigurationException invalid() {
        return new ConfigurationException(422, "ANALYSIS_HIT_INVALID", "可信分析命中结构或配置无效");
    }

    private ConfigurationException unavailable() {
        return new ConfigurationException(
                422, "ANALYSIS_CONFIGURATION_UNAVAILABLE", "分析策略或提供商未启用、未验证或不属于当前租户");
    }
}
