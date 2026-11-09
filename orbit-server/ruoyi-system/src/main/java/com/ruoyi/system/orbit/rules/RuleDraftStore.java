package com.ruoyi.system.orbit.rules;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 仅内部草稿/暂停/归档存储；没有HTTP入口或启用入口，范围/profile及公共菜单动作授权尚未接通。 */
@Service
public class RuleDraftStore {
    private final RuleDraftMapper mapper;
    private final RuleWriteGuard guard;
    private final RuleOwnership ownership;

    public RuleDraftStore(RuleDraftMapper mapper, RuleWriteGuard guard, RuleOwnership ownership) {
        this.mapper = mapper;
        this.guard = guard;
        this.ownership = ownership;
    }

    /** 内部持久化行不是公共Rule DTO；正文默认不参与JSON序列化和日志。 */
    public static class Row {
        public String id, tenantId, state, bodyHash, requestHash, action;
        public long revision;
        @JsonIgnore public String bodyJson;
        public Instant createdAt;

        @Override
        public String toString() {
            return "RuleDraft[REDACTED]";
        }
    }

    public static final class Failure extends RuntimeException {
        private final int status;

        public Failure(int status, String safeMessage) {
            super(safeMessage);
            this.status = status;
        }

        public int status() {
            return status;
        }
    }

    /** expectedRevision=0且id=null表示新草稿；其他情况必须精确匹配已存在版本。 */
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Row saveTrustedDraft(
            String tenant,
            long actor,
            String key,
            String id,
            long expectedRevision,
            JsonNode request,
            String reason) {
        RuleWriteGuard.Frozen frozen = guard.prepare(request);
        return mutate(tenant, actor, key, id, expectedRevision, "SAVE", frozen, reason);
    }

    /** 仅暂停或归档；启用必须另接可信模拟/范围/profile验证，不能从本入口绕过。 */
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Row transitionTrusted(
            String tenant,
            long actor,
            String key,
            String id,
            long expectedRevision,
            String action,
            String reason) {
        if (!Set.of("PAUSE", "ARCHIVE").contains(action == null ? "" : action))
            throw new Failure(422, "规则转换入口不允许该操作");
        return mutate(tenant, actor, key, id, expectedRevision, action, null, reason);
    }

    private Row mutate(
            String tenant,
            long actor,
            String key,
            String id,
            long expectedRevision,
            String action,
            RuleWriteGuard.Frozen frozen,
            String reason) {
        tenant = RuleWriteGuard.uuid(tenant);
        key = RuleWriteGuard.uuid(key);
        if (actor < 1
                || expectedRevision < 0
                || expectedRevision >= 9007199254740991L
                || (id == null && (expectedRevision != 0 || !action.equals("SAVE")))
                || (id != null && expectedRevision == 0)) throw new Failure(422, "规则身份或版本无效");
        if (id != null) id = RuleWriteGuard.uuid(id);
        reason = RuleWriteGuard.normalize(reason, 500);
        if (!Integer.valueOf(1).equals(mapper.activeTenant(tenant)))
            throw new Failure(404, "规则租户不可用");
        var actorScope = ownership.actor(tenant, actor);
        String hash =
                hash(
                        List.of(
                                tenant,
                                actor,
                                action,
                                id == null ? "CREATE" : id,
                                expectedRevision,
                                frozen == null ? "" : frozen.hash(),
                                reason));
        mapper.reserve(tenant, actor, key, hash);
        Row replay = mapper.replay(tenant, actor, key);
        if (!hash.equals(replay.requestHash)) throw new Failure(409, "幂等键已用于不同规则请求");
        if (replay.id != null) {
            Row current = mapper.lock(tenant, replay.id);
            if (current == null) throw new Failure(404, "规则不存在或不可见");
            ownership.require(tenant, actor, actorScope, current.bodyJson, false);
            return mapper.version(tenant, replay.id, replay.revision);
        }
        Row row = id == null ? new Row() : mapper.lock(tenant, id);
        if (row == null) throw new Failure(404, "规则不存在或不可见");
        if (id != null) ownership.require(tenant, actor, actorScope, row.bodyJson, false);
        if (frozen != null) ownership.require(tenant, actor, actorScope, frozen.body(), true);
        if (id != null && row.revision != expectedRevision) throw new Failure(409, "规则版本已变化");
        if (id == null) {
            row.id = UUID.randomUUID().toString();
            row.tenantId = tenant;
            row.state = "DRAFT";
        } else if (row.state.equals("ARCHIVED")) throw new Failure(409, "归档规则不可再修改");
        if (action.equals("SAVE")) {
            if (row.state.equals("ENABLED")) throw new Failure(409, "请先暂停已启用规则再编辑");
            row.bodyJson = frozen.body();
            row.bodyHash = frozen.hash();
        } else if (action.equals("PAUSE")) {
            if (!row.state.equals("ENABLED")) throw new Failure(409, "仅启用规则可以暂停");
            row.state = "PAUSED";
        } else {
            if (row.state.equals("ENABLED")) throw new Failure(409, "请先暂停已启用规则再归档");
            row.state = "ARCHIVED";
        }
        row.revision = expectedRevision + 1;
        row.createdAt = Instant.now();
        row.action = action;
        if (id == null) mapper.insert(row);
        else if (mapper.update(row) != 1) throw new Failure(409, "规则版本已变化");
        mapper.freeze(row);
        mapper.event(row, actor, reason);
        mapper.finish(tenant, actor, key, row);
        return row;
    }

    private String hash(Object value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(
                                            new ObjectMapper()
                                                    .writeValueAsString(value)
                                                    .getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new Failure(422, "规则幂等内容无法处理");
        }
    }
}
