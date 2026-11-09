package com.ruoyi.system.orbit.scope;

import com.ruoyi.system.orbit.rules.*;
import java.text.Normalizer;
import java.util.*;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 内部目录增量发布；仅可信服务调用，不能把输入标记为真实平台已验证。 */
@Service
public class AccountDirectoryPublisher {
    public record Entry(
            String id,
            String externalId,
            String name,
            String operator,
            String team,
            String vendor,
            String currency,
            String accountStatus,
            String authStatus) {
        @Override
        public String toString() {
            return "DirectoryEntry[REDACTED]";
        }
    }

    private final AccountScopeMapper mapper;
    private final RuleDraftMapper identities;
    private final RuleOwnership ownership;

    public AccountDirectoryPublisher(
            AccountScopeMapper mapper, RuleDraftMapper identities, RuleOwnership ownership) {
        this.mapper = mapper;
        this.identities = identities;
        this.ownership = ownership;
    }

    /** 目录时钟与冻结共用行锁；CAS拒绝迟到发布，批内任意失败回滚全部成员及版本。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public long publishTrusted(
            String tenant,
            long actor,
            long expectedRevision,
            List<Entry> changes,
            List<String> removals) {
        tenant = requiredUuid(tenant);
        if (expectedRevision < 1
                || expectedRevision == Long.MAX_VALUE
                || changes == null
                || removals == null
                || changes.size() + (long) removals.size() < 1
                || changes.size() + (long) removals.size() > 1000) throw invalid();
        List<Entry> prepared =
                changes.stream()
                        .map(this::prepare)
                        .sorted(Comparator.comparing(Entry::id))
                        .toList();
        List<String> deleted = removals.stream().map(this::requiredUuid).sorted().toList();
        Set<String> ids = new HashSet<>();
        for (Entry entry : prepared) if (!ids.add(entry.id())) throw invalid();
        for (String id : deleted) if (!ids.add(id)) throw invalid();
        var principal = ownership.actor(tenant, actor);
        if (!"SUPER_ADMIN".equals(principal.dataRole))
            throw new AccountScopeService.Failure(403, "当前身份不允许发布账户目录");
        mapper.reserveClock(tenant);
        if (mapper.clock(tenant) != expectedRevision)
            throw new AccountScopeService.Failure(409, "账户目录版本已变化，请重新读取后发布");
        long next = expectedRevision + 1;
        for (Entry entry : prepared) {
            // 账户归属必须对应当前有效业务成员；不接受跨租户或已停用主体。
            if (entry.team() != null
                    && !Integer.valueOf(1).equals(identities.ownershipTeam(tenant, entry.team())))
                throw invalid();
            if (entry.operator() != null) {
                var owner = identities.ownershipOwner(tenant, entry.operator());
                if (owner == null || !owner.usable || !owner.teamId.equals(entry.team()))
                    throw invalid();
            }
            try {
                // 按账户主键更新，不能用外部ID唯一键冲突把另一账户覆盖。
                if (mapper.directoryExists(tenant, entry.id()))
                    mapper.updateDirectory(tenant, entry, next);
                else mapper.insertDirectory(tenant, entry, next);
            } catch (DataIntegrityViolationException error) {
                throw new AccountScopeService.Failure(409, "账户目录标识冲突");
            }
        }
        for (String id : deleted)
            if (mapper.deleteDirectory(tenant, id) != 1)
                throw new AccountScopeService.Failure(404, "待移除账户不存在于当前目录");
        mapper.advanceClock(tenant, next);
        return next;
    }

    private Entry prepare(Entry input) {
        if (input == null
                || input.externalId() == null
                || !input.externalId().matches("[0-9]{1,64}")
                || input.name() == null
                || input.currency() == null
                || !input.currency().matches("[A-Z]{3}")
                || !Set.of("ACTIVE", "DISABLED", "UNKNOWN")
                        .contains(Objects.toString(input.accountStatus(), ""))
                || !Set.of("AUTHORIZED", "EXPIRED", "REVOKED", "UNKNOWN")
                        .contains(Objects.toString(input.authStatus(), ""))) throw invalid();
        String name = Normalizer.normalize(input.name(), Normalizer.Form.NFC);
        if (name.isBlank()
                || name.codePointCount(0, name.length()) > 10000
                || name.codePoints().anyMatch(Character::isISOControl)) throw invalid();
        return new Entry(
                requiredUuid(input.id()),
                input.externalId(),
                name,
                nullableUuid(input.operator()),
                nullableUuid(input.team()),
                nullableUuid(input.vendor()),
                input.currency(),
                input.accountStatus(),
                input.authStatus());
    }

    private String nullableUuid(String value) {
        return value == null ? null : requiredUuid(value);
    }

    private String requiredUuid(String value) {
        try {
            return ScopeRequestGuard.uuid(value);
        } catch (IllegalArgumentException error) {
            throw invalid();
        }
    }

    private AccountScopeService.Failure invalid() {
        return new AccountScopeService.Failure(422, "账户目录字段、批次或当前归属关系无效");
    }
}
