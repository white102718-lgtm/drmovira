package com.adpulse.main.migration;

import static com.adpulse.main.migration.AssetMigrationService.require;
import static com.adpulse.main.migration.ChannelIncrementModels.*;

import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

/** 将老库新增渠道按环境增量写入当前目标库，并持久化不可变映射。 */
public class ChannelIncrementService {
    private final AssetMigrationMapper mapper;
    private final LegacyAssetReader reader;
    private final AssetMigrationProperties properties;
    private final ChannelMigrationMappingResolver mappings;
    private final ObjectMapper json;

    public ChannelIncrementService(
            AssetMigrationMapper mapper,
            LegacyAssetReader reader,
            AssetMigrationProperties properties,
            ChannelMigrationMappingResolver mappings,
            ObjectMapper json) {
        this.mapper = mapper;
        this.reader = reader;
        this.properties = properties;
        this.mappings = mappings;
        this.json = json;
    }

    /** 扫描未映射渠道；空 sourceIds 表示返回全部缺口。 */
    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ, timeout = 180)
    public Plan plan(PlanRequest request) {
        authorize();
        checkEnvironment();
        var snapshot = reader.readChannelSnapshot();
        return buildPlan(
                parseIds(request == null ? null : request.sourceIds()),
                snapshot.channels(),
                snapshot.rates());
    }

    /** 重新计算并核对计划后，在单个目标库事务中写入渠道、费率和审计映射。 */
    @Transactional(isolation = Isolation.REPEATABLE_READ, timeout = 180)
    public ExecuteResult execute(ExecuteRequest request) {
        long operatorId = authorize();
        require(request != null && request.confirmed(), "必须明确确认执行渠道增量迁移");
        Set<Long> selected = parseIds(request.sourceIds());
        require(!selected.isEmpty(), "至少选择一个来源渠道");
        checkEnvironment();
        mapper.lockMutex();
        require(mapper.channelIncrementSchemaReady() == 1, "渠道增量迁移表尚未初始化");
        require(mapper.channelWriteSchemaReady() == 1, "请先将渠道编码改为允许 NULL，并确认渠道表使用 InnoDB");
        String selectedJson = encode(selected.stream().sorted().map(String::valueOf).toList());
        ExecuteResult previous =
                mapper.appliedChannelIncrement(
                        properties.getTargetEnvironment().name(),
                        properties.getSourceUuid(),
                        properties.getTargetUuid(),
                        properties.getSourceSchema(),
                        properties.getTargetSchema(),
                        operatorId,
                        request.planHash(),
                        selectedJson);
        if (previous != null) return previous;
        require(mapper.nextJob() == null, "账户迁移任务正在运行，请完成后再同步渠道");
        mapper.channels(true);
        var snapshot = reader.readChannelSnapshot();
        List<LegacyChannel> sourceChannels = snapshot.channels();
        List<LegacyRate> sourceRates = snapshot.rates();
        Plan plan = buildPlan(selected, sourceChannels, sourceRates);
        require(Objects.equals(plan.planHash(), request.planHash()), "来源或目标已变化，请重新预检");
        require(plan.items().size() == selected.size(), "选择中包含已映射渠道，请重新预检");
        require(plan.items().stream().noneMatch(item -> item.conflict() != null), "存在渠道名称或编码冲突");
        require(mapper.activeOperator(operatorId) == 1, "迁移操作员已停用或删除");

        Map<Long, LegacyChannel> channels =
                sourceChannels.stream()
                        .collect(Collectors.toMap(LegacyChannel::sourceId, Function.identity()));
        Map<Long, List<LegacyRate>> rates =
                sourceRates.stream().collect(Collectors.groupingBy(LegacyRate::sourceChannelId));
        String batchKey =
                "channel-increment-"
                        + properties.getTargetEnvironment().name().toLowerCase(Locale.ROOT)
                        + "-"
                        + UUID.randomUUID();
        int rateCount = 0;
        for (Long sourceId : selected.stream().sorted().toList()) {
            LegacyChannel source = Objects.requireNonNull(channels.get(sourceId));
            validate(source);
            AppliedChannel applied = new AppliedChannel(source);
            mapper.insertIncrementChannel(applied, operatorId);
            for (LegacyRate rate : rates.getOrDefault(sourceId, List.of())) {
                validate(rate);
                mapper.insertIncrementRate(applied.getTargetId(), rate, operatorId);
                rateCount++;
            }
            mapper.insertIncrementMapping(
                    properties.getTargetEnvironment().name(),
                    properties.getSourceUuid(),
                    properties.getSourceSchema(),
                    properties.getTargetUuid(),
                    properties.getTargetSchema(),
                    sourceId,
                    applied.getTargetId(),
                    batchKey,
                    operatorId);
        }
        mapper.insertIncrementBatch(
                batchKey,
                properties.getTargetEnvironment().name(),
                plan.planHash(),
                properties.getSourceUuid(),
                properties.getSourceSchema(),
                properties.getTargetUuid(),
                properties.getTargetSchema(),
                encode(
                        Map.of(
                                "selectedIds",
                                selected.stream().sorted().map(String::valueOf).toList(),
                                "channelCount",
                                selected.size(),
                                "rateCount",
                                rateCount,
                                "plan",
                                plan,
                                "channels",
                                sourceChannels.stream()
                                        .filter(c -> selected.contains(c.sourceId()))
                                        .toList(),
                                "rates",
                                sourceRates.stream()
                                        .filter(r -> selected.contains(r.sourceChannelId()))
                                        .toList())),
                operatorId);
        mappings.evict();
        return new ExecuteResult(
                batchKey, properties.getTargetEnvironment().name(), selected.size(), rateCount);
    }

    private Plan buildPlan(
            Set<Long> selected, List<LegacyChannel> source, List<LegacyRate> sourceRates) {
        var sourceIds = source.stream().map(LegacyChannel::sourceId).collect(Collectors.toSet());
        require(selected.isEmpty() || sourceIds.containsAll(selected), "选择中包含不存在的来源渠道");
        var mapping = mappings.resolveForChannelPlan();
        Map<Long, Long> existing = mapping.ids();
        var rates =
                sourceRates.stream()
                        .collect(
                                Collectors.groupingBy(
                                        LegacyRate::sourceChannelId, Collectors.counting()));
        List<LegacyChannel> missing =
                source.stream()
                        .filter(channel -> !existing.containsKey(channel.sourceId()))
                        .sorted(Comparator.comparingLong(LegacyChannel::sourceId))
                        .toList();
        List<Candidate> items =
                missing.stream()
                        .map(
                                channel -> {
                                    String problem = null;
                                    try {
                                        validate(channel);
                                        var channelRates =
                                                sourceRates.stream()
                                                        .filter(
                                                                r ->
                                                                        r.sourceChannelId()
                                                                                == channel
                                                                                        .sourceId())
                                                        .toList();
                                        channelRates.forEach(ChannelIncrementService::validate);
                                        for (int i = 0; i < channelRates.size(); i++) {
                                            for (int j = i + 1; j < channelRates.size(); j++) {
                                                require(
                                                        endsBefore(
                                                                        channelRates.get(i),
                                                                        channelRates.get(j))
                                                                || endsBefore(
                                                                        channelRates.get(j),
                                                                        channelRates.get(i)),
                                                        "来源渠道费率有效期重叠");
                                            }
                                        }
                                    } catch (AssetMigrationService.Conflict exception) {
                                        problem = exception.getMessage();
                                    }
                                    TargetConflict conflict =
                                            mapper.channelConflict(
                                                    channel.channelName(), channel.channelCode());
                                    return new Candidate(
                                            Long.toString(channel.sourceId()),
                                            channel.channelName(),
                                            channel.channelCode(),
                                            Math.toIntExact(
                                                    rates.getOrDefault(channel.sourceId(), 0L)),
                                            conflict == null && problem == null
                                                    ? "INSERT"
                                                    : "CONFLICT",
                                            problem != null
                                                    ? problem
                                                    : conflict == null
                                                            ? null
                                                            : "与目标渠道 "
                                                                    + conflict.id()
                                                                    + " 的名称或编码冲突");
                                })
                        .toList();
        List<LegacyRate> selectedRates =
                sourceRates.stream()
                        .filter(
                                rate ->
                                        missing.stream()
                                                .anyMatch(
                                                        channel ->
                                                                channel.sourceId()
                                                                        == rate.sourceChannelId()))
                        .toList();
        String body =
                properties.getTargetEnvironment().name()
                        + "|"
                        + encode(missing)
                        + "|"
                        + encode(selectedRates)
                        + "|"
                        + encode(items)
                        + "|"
                        + mapping.version();
        return new Plan(
                properties.getTargetEnvironment().name(),
                sha256(body),
                source.size(),
                existing.size(),
                items.size(),
                items.stream()
                        .filter(
                                item ->
                                        selected.isEmpty()
                                                || selected.contains(
                                                        Long.parseLong(item.sourceId())))
                        .toList());
    }

    private void checkEnvironment() {
        properties.validateEnvironment();
        var identity = mapper.identity();
        require(
                properties.getTargetUuid().equals(identity.serverUuid())
                        && properties.getTargetSchema().equals(identity.schemaName()),
                "目标实例或库名不符");
    }

    private long authorize() {
        var authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null
                || !(authentication.getPrincipal() instanceof CurrentUser user)
                || !properties.getOperatorIds().contains(user.userId())) {
            throw new AccessDeniedException("未配置迁移操作权限");
        }
        return user.userId();
    }

    private static Set<Long> parseIds(List<String> values) {
        if (values == null || values.isEmpty()) return Set.of();
        try {
            Set<Long> ids =
                    values.stream()
                            .map(Long::parseLong)
                            .collect(Collectors.toCollection(LinkedHashSet::new));
            require(ids.stream().allMatch(id -> id > 0), "来源渠道 ID 不合法");
            return ids;
        } catch (NumberFormatException exception) {
            throw new AssetMigrationService.Conflict("来源渠道 ID 不合法");
        }
    }

    private static void validate(LegacyChannel value) {
        require(value.tenantId() == 0, "来源渠道租户不符合迁移范围");
        require(
                value.channelName() != null
                        && !value.channelName().isBlank()
                        && value.channelName().length() <= 50,
                "来源渠道名称不合法");
        require(length(value.channelShortName(), 15), "来源渠道简称超长");
        require(
                value.channelCode() == null
                        || value.channelCode().isBlank()
                        || value.channelCode().matches("[a-zA-Z0-9]{1,10}"),
                "来源渠道编码不合法");
        require(value.channelType() == 1 || value.channelType() == 2, "来源渠道类型不合法");
        require(value.status() == 0 || value.status() == 1, "来源渠道状态不合法");
        require(value.createdAt() != null && value.updatedAt() != null, "来源渠道时间为空");
        require(length(value.belongTeam(), 50) && value.belongTeam() != null, "来源所属团队不合法");
        require(
                value.settlementMethod() != null
                        && !value.settlementMethod().isBlank()
                        && length(value.settlementMethod(), 50),
                "来源结算方式不合法");
        require(
                value.settlementCurrency() == null
                        || value.settlementCurrency().isBlank()
                        || Set.of("USD", "U", "RMB").contains(value.settlementCurrency()),
                "来源结算币种需人工确认");
        require(
                value.paymentAddress() != null
                        && !value.paymentAddress().isBlank()
                        && length(value.paymentAddress(), 1000),
                "来源收款地址不合法");
        require(
                value.loginUrl() != null
                        && !value.loginUrl().isBlank()
                        && length(value.loginUrl(), 1000),
                "来源登录链接不合法");
        require(
                length(value.remark(), 500)
                        && length(value.tgGroupId(), 64)
                        && length(value.tgGroupName(), 100),
                "来源渠道文本字段超长");
        require(!"买断".equals(value.settlementMethod()) || value.buyoutAmount() != null, "买断渠道金额为空");
    }

    private static void validate(LegacyRate value) {
        require(
                value.damageRate() == null
                        && value.openingFee() == null
                        && value.openingFeeUnit() == null,
                "来源费率存在目标未承载字段");
        require(value.effectiveDate() != null, "来源费率生效日为空");
        require(
                value.expiryDate() == null || !value.expiryDate().isBefore(value.effectiveDate()),
                "来源费率日期倒置");
        require(nonNegative(value.serviceFee()) && nonNegative(value.rebateRate()), "来源费率金额不合法");
        LocalDate today = LocalDate.now(ZoneOffset.ofHours(8));
        int expected =
                value.effectiveDate().isAfter(today)
                        ? 2
                        : value.expiryDate() != null && value.expiryDate().isBefore(today) ? 0 : 1;
        require(value.status() != null && value.status() == expected, "来源费率状态与有效期不一致");
    }

    private static boolean endsBefore(LegacyRate left, LegacyRate right) {
        return left.expiryDate() != null && left.expiryDate().isBefore(right.effectiveDate());
    }

    private static boolean length(String value, int maximum) {
        return value == null || value.length() <= maximum;
    }

    private static boolean nonNegative(BigDecimal value) {
        return value != null && value.signum() >= 0;
    }

    private String encode(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new AssetMigrationService.Conflict("迁移计划序列化失败");
        }
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
