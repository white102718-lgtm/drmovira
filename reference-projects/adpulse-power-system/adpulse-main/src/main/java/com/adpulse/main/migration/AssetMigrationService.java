package com.adpulse.main.migration;

import com.adpulse.main.migration.AssetMigrationModels.*;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/** 固化预检计划，按批事务执行；数据库互斥行保证多实例与重启不会重复提交。 */
public class AssetMigrationService {
    private static final Logger LOG = LoggerFactory.getLogger(AssetMigrationService.class);
    private final AssetMigrationMapper mapper;
    private final LegacyAssetReader reader;
    private final AssetMigrationProperties properties;
    private final ObjectMapper json;
    private final TransactionTemplate transaction;
    private final ChannelMigrationMappingResolver channelMappings;

    public AssetMigrationService(
            AssetMigrationMapper mapper,
            LegacyAssetReader reader,
            AssetMigrationProperties properties,
            ObjectMapper json,
            PlatformTransactionManager manager,
            ChannelMigrationMappingResolver channelMappings) {
        this.mapper = mapper;
        this.reader = reader;
        this.properties = properties;
        this.json = json;
        this.channelMappings = channelMappings;
        transaction = new TransactionTemplate(manager);
        // 缺失账户的范围锁同样重要：目标唯一键不只是 account_id。
        transaction.setIsolationLevel(TransactionDefinition.ISOLATION_REPEATABLE_READ);
        transaction.setTimeout(180);
    }

    /** 创建异步预检，业务表不发生变更。 */
    public Job plan() {
        long actor = authorize();
        properties.validateSource();
        return transaction.execute(
                status -> {
                    mapper.lockMutex();
                    checkTarget();
                    require(mapper.nextJob() == null, "已有迁移任务正在运行");
                    Job job = new Job();
                    job.setId(UUID.randomUUID().toString());
                    job.setState("QUEUED");
                    job.setOperatorId(actor);
                    mapper.insertJob(job);
                    return job;
                });
    }

    /** 调用前核对当前服务实际连接的环境；不要求迁移辅助表已经创建。 */
    public EnvironmentView environment() {
        authorize();
        checkIdentity();
        return new EnvironmentView(
                properties.getTargetEnvironment().name(),
                properties.getSourceUuid(),
                properties.getSourceSchema(),
                properties.getTargetUuid(),
                properties.getTargetSchema(),
                properties.channelLedgerTable(),
                properties.channelBatchKey(),
                properties.isMappingCacheEnabled());
    }

    /** 获取持久化进度。 */
    public Job status(String id) {
        authorize();
        return find(id);
    }

    /** 恢复当前登录操作员的近期任务，任务状态以数据库为准。 */
    public List<JobView> recentJobs() {
        return mapper.recentJobs(authorize()).stream().map(JobView::of).toList();
    }

    /** 分页读取待执行、已完成或隔离明细。 */
    public Items items(String id, long afterId, String state) {
        authorize();
        find(id);
        require(afterId >= 0, "分页游标不合法");
        require(state == null || Set.of("PENDING", "DONE", "ISOLATED").contains(state), "明细状态不合法");
        var items = mapper.items(id, afterId, state);
        return new Items(
                items.stream().map(ItemView::of).toList(),
                items.size() == 250 ? Long.toString(items.getLast().getId()) : null);
    }

    /** 只有计划哈希匹配才能启动；重复请求返回已有状态，不再次迁移。 */
    public Job execute(String id, Execute request) {
        long actor = authorize();
        return transaction.execute(
                status -> {
                    mapper.lockMutex();
                    Job job = find(id);
                    require(job.getOperatorId() == actor, "仅预检创建人可启动该计划");
                    require(
                            Objects.equals(job.getPlanHash(), request.planHash())
                                    && job.getPlanHash() != null,
                            "计划哈希不匹配");
                    require(
                            request.acceptAvailableInventory() && request.acceptAutomaticSync(),
                            "请先确认新增库存为 AVAILABLE，且后续飞书同步可覆盖业务资料");
                    if (Set.of("VALIDATING", "APPLYING", "DONE", "DONE_WITH_ISSUES")
                            .contains(job.getState())) return job;
                    require("READY".equals(job.getState()), "任务不是待执行计划，请重新预检");
                    properties.validateSource();
                    require(mapper.nextJob() == null, "已有迁移任务正在运行");
                    checkTarget();
                    job.setState("VALIDATING");
                    mapper.saveJob(job);
                    return job;
                });
    }

    /** 定时工作器每轮最多提交 250 个账户；进程退出时未提交事务由数据库回滚。 */
    public void tick() {
        String[] currentId = {null};
        String[] phase = {"读取任务"};
        try {
            transaction.executeWithoutResult(
                    status -> {
                        mapper.lockMutex();
                        Job job = mapper.nextJob();
                        if (job == null) return;
                        currentId[0] = job.getId();
                        phase[0] = job.getState();
                        checkTarget();
                        require(
                                properties.getOperatorIds().contains(job.getOperatorId())
                                        && mapper.activeOperator(job.getOperatorId()) == 1,
                                "任务操作员已失效或不在迁移白名单中");
                        switch (job.getState()) {
                            case "QUEUED" -> prepare(job);
                            case "VALIDATING" -> validateSource(job);
                            case "APPLYING" -> applyBatch(job);
                            default -> throw new Conflict("任务状态异常");
                        }
                        mapper.saveJob(job);
                    });
        } catch (RuntimeException exception) {
            if (currentId[0] == null) throw exception;
            String diagnostic = safeDiagnostic(exception, phase[0]);
            LOG.warn(
                    "渠道账户迁移失败 taskId={} stage={} diagnostic={}",
                    currentId[0],
                    phase[0],
                    diagnostic);
            // 失败事务已回滚；另起事务记录失败。禁止记录原始 SQL、凭据或整条账户数据。
            transaction.executeWithoutResult(
                    status -> {
                        mapper.lockMutex();
                        Job job = find(currentId[0]);
                        if (!Set.of("QUEUED", "VALIDATING", "APPLYING").contains(job.getState()))
                            return;
                        job.setState("FAILED");
                        job.setError(
                                exception instanceof Conflict
                                        ? exception.getMessage()
                                        : diagnostic);
                        mapper.saveJob(job);
                    });
        }
    }

    /** 只记录异常类型与代码位置，保留定位能力，禁止输出可能携带凭据的异常 message。 */
    static String safeDiagnostic(Throwable exception, String phase) {
        Throwable root = exception;
        for (int depth = 0;
                depth < 16 && root.getCause() != null && root.getCause() != root;
                depth++) root = root.getCause();
        String location =
                Arrays.stream(root.getStackTrace())
                        .filter(
                                frame ->
                                        frame.getClassName()
                                                .startsWith("com.adpulse.main.migration."))
                        .findFirst()
                        .map(frame -> frame.getFileName() + ":" + frame.getLineNumber())
                        .orElse("未知位置");
        String message =
                phase
                        + "失败："
                        + exception.getClass().getSimpleName()
                        + "；根因="
                        + root.getClass().getSimpleName()
                        + "；位置="
                        + location;
        return message.substring(0, Math.min(message.length(), 250));
    }

    private void prepare(Job job) {
        var snapshot = channelMappings.resolve();
        var channelIds = snapshot.ids();
        var channels =
                mapper.channels(false).stream()
                        .collect(Collectors.toMap(Channel::id, Function.identity()));
        var sources = reader.read();
        require(!sources.isEmpty(), "来源账户为空，停止预检");
        require(sources.stream().allMatch(row -> row.tenantId() == 0), "发现非预期租户");
        var missing =
                sources.stream()
                        .map(Source::channelId)
                        .distinct()
                        .filter(
                                id ->
                                        !channelIds.containsKey(id)
                                                || !channels.containsKey(channelIds.get(id)))
                        .sorted(Comparator.nullsFirst(Comparator.naturalOrder()))
                        .toList();
        require(
                missing.isEmpty(),
                "渠道映射不完整或目标已删除，共 "
                        + missing.size()
                        + " 个；老渠道ID："
                        + missing.stream()
                                .limit(12)
                                .map(String::valueOf)
                                .collect(Collectors.joining(","))
                        + "。请先在渠道同步页处理，再重新预检账户");
        job.setSourceHash(hash(encode(sources)));
        job.setChannelHash(snapshot.version());
        job.setSourceCount(sources.size());
        var grouped = new LinkedHashMap<String, List<Source>>();
        for (Source source : sources)
            grouped.computeIfAbsent(normalize(source.accountId()), key -> new ArrayList<>())
                    .add(source);
        var plans = new ArrayList<Item>();
        var groups = new ArrayList<>(grouped.entrySet());
        var attributes = new HashSet<>(mapper.attributes());
        for (int offset = 0; offset < groups.size(); offset += 250) {
            var batch = groups.subList(offset, Math.min(offset + 250, groups.size()));
            var keys =
                    batch.stream()
                            .map(Map.Entry::getKey)
                            .filter(AssetMigrationService::validAccountId)
                            .toList();
            var existing =
                    keys.isEmpty()
                            ? Map.<String, List<Asset>>of()
                            : index(mapper.assets(keys, false));
            for (var group : batch) {
                Item item =
                        prepareItem(
                                job.getId(),
                                group.getKey(),
                                group.getValue(),
                                existing.getOrDefault(group.getKey(), List.of()),
                                channelIds,
                                channels,
                                attributes);
                plans.add(item);
                job.setDuplicates(job.getDuplicates() + group.getValue().size() - 1);
                if ("ISOLATED".equals(item.getState())) job.setIsolated(job.getIsolated() + 1);
                else job.setTotal(job.getTotal() + 1);
            }
        }
        job.setPlanHash(hash(job.getSourceHash() + job.getChannelHash() + encode(plans)));
        for (int offset = 0; offset < plans.size(); offset += 250)
            mapper.insertItems(plans.subList(offset, Math.min(offset + 250, plans.size())));
        job.setState("READY");
    }

    private Item prepareItem(
            String jobId,
            String accountId,
            List<Source> sources,
            List<Asset> targets,
            Map<Long, Long> mapping,
            Map<Long, Channel> channels,
            Set<String> attributes) {
        Item item = new Item();
        item.setJobId(jobId);
        item.setAccountId(accountId);
        item.setSourceJson(encode(sources));
        item.setAction("ISOLATE");
        item.setState("ISOLATED");
        Source source = sources.getFirst();
        if (!validAccountId(accountId)) return isolate(item, "账户 ID 不是 1～100 位数字，需人工确认");
        if (sources.stream().anyMatch(row -> !sameSource(source, row)))
            return isolate(item, "同一账户的来源五字段不一致");
        if (targets.size() > 1) return isolate(item, "目标存在多条有效资产");
        if (source.accountType() != null && source.accountType().length() > 100)
            return isolate(item, "账户类型超长");
        String attribute = attribute(source.attribute());
        if ("UNKNOWN".equals(attribute) || (attribute != null && !attributes.contains(attribute)))
            return isolate(item, "属性编码未知或目标属性未配置");
        Asset target = targets.isEmpty() ? null : targets.getFirst();
        if (target != null) {
            item.setTargetId(target.id());
            item.setBeforeJson(encode(target));
            if (target.manual() != 0) return isolate(item, "目标已人工锁定");
            if (attribute != null
                    && target.accountAttribute() != null
                    && !target.accountAttribute().isBlank()
                    && !attribute.equals(target.accountAttribute()))
                return isolate(item, "非空账户属性冲突");
            if (attribute == null) attribute = target.accountAttribute();
        }
        Channel channel = channels.get(mapping.get(source.channelId()));
        Values desired =
                new Values(
                        accountId,
                        channel.id(),
                        channel.channelName(),
                        source.accountType(),
                        attribute);
        item.setDesiredJson(encode(desired));
        item.setAction(
                target == null
                        ? "INSERT"
                        : desired.equals(target.values()) ? "UNCHANGED" : "UPDATE");
        item.setState("PENDING");
        return item;
    }

    private void validateSource(Job job) {
        require(job.getSourceHash().equals(hash(encode(reader.read()))), "来源已变化，请重新预检");
        require(
                job.getChannelHash().equals(channelMappings.resolve().version()),
                "环境或渠道迁移账本已变化，请重新预检");
        job.setState("APPLYING");
    }

    private void applyBatch(Job job) {
        require(
                job.getChannelHash().equals(channelMappings.resolve().version()),
                "环境或渠道迁移账本已变化，任务停止");
        var items = mapper.items(job.getId(), 0, "PENDING");
        if (items.isEmpty()) {
            require(job.getCompleted() == job.getTotal(), "任务计数不守恒");
            job.setState(job.getIsolated() == 0 ? "DONE" : "DONE_WITH_ISSUES");
            return;
        }
        var channels =
                mapper.channels(true).stream()
                        .collect(Collectors.toMap(Channel::id, Function.identity()));
        var attributes = new HashSet<>(mapper.attributes());
        var keys = items.stream().map(Item::getAccountId).toList();
        // REPEATABLE READ 下锁住匹配记录及缺失 ID 的索引间隙；与并行新增互斥。
        var existing = index(mapper.assets(keys, true));
        for (Item item : items) {
            Values desired = decode(item.getDesiredJson(), Values.class);
            Channel channel = channels.get(desired.channelId());
            require(
                    channel != null && Objects.equals(channel.channelName(), desired.channelName()),
                    "渠道已修改或删除，请重新预检");
            require(
                    desired.accountAttribute() == null
                            || attributes.contains(desired.accountAttribute()),
                    "目标属性配置发生变化");
            var matches = existing.getOrDefault(item.getAccountId(), List.of());
            if ("INSERT".equals(item.getAction())) require(matches.isEmpty(), "计划新增的账户已存在，请重新预检");
            else
                require(
                        matches.size() == 1
                                && matches.getFirst()
                                        .equals(decode(item.getBeforeJson(), Asset.class)),
                        "目标账户已变化，本批回滚；请重新预检");
        }
        var updates = items.stream().filter(item -> "UPDATE".equals(item.getAction())).toList();
        var inserts = items.stream().filter(item -> "INSERT".equals(item.getAction())).toList();
        if (!updates.isEmpty()) mapper.updateAssets(updates);
        if (!inserts.isEmpty())
            require(mapper.insertAssets(inserts, job.getOperatorId()) == inserts.size(), "新增数量不符");
        var after = index(mapper.assets(keys, true));
        for (Item item : items) {
            var matches = after.getOrDefault(item.getAccountId(), List.of());
            require(
                    matches.size() == 1
                            && matches.getFirst()
                                    .values()
                                    .equals(decode(item.getDesiredJson(), Values.class)),
                    "执行后五字段校验失败");
            item.setTargetId(matches.getFirst().id());
            item.setAfterJson(encode(matches.getFirst()));
        }
        mapper.finishItems(items);
        job.setCompleted(job.getCompleted() + items.size());
    }

    private long authorize() {
        var authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null
                || !(authentication.getPrincipal() instanceof CurrentUser user)
                || !properties.getOperatorIds().contains(user.userId()))
            throw new AccessDeniedException("未配置迁移操作权限");
        return user.userId();
    }

    private Job find(String id) {
        Job job = mapper.job(id);
        require(job != null, "迁移任务不存在");
        return job;
    }

    private void checkTarget() {
        checkIdentity();
        require(mapper.schemaReady() == 1, "目标表默认值或事务引擎不符合迁移要求");
    }

    private void checkIdentity() {
        properties.validateEnvironment();
        Identity identity = mapper.identity();
        require(
                properties.getTargetUuid().equals(identity.serverUuid())
                        && properties.getTargetSchema().equals(identity.schemaName()),
                "目标实例或库名不符");
    }

    static String normalize(String value) {
        String normalized = value == null ? "" : value.trim();
        return normalized.startsWith("act_") ? normalized.substring(4) : normalized;
    }

    static boolean validAccountId(String value) {
        return value.matches("[0-9]{1,100}");
    }

    static String attribute(Integer value) {
        if (value == null) return null;
        return switch (value) {
            case 1 -> "普通户";
            case 2 -> "准稳户";
            case 3 -> "稳定户";
            default -> "UNKNOWN";
        };
    }

    static boolean sameSource(Source left, Source right) {
        return Objects.equals(left.channelId(), right.channelId())
                && Objects.equals(left.accountType(), right.accountType())
                && Objects.equals(left.attribute(), right.attribute());
    }

    private Item isolate(Item item, String reason) {
        item.setReason(reason);
        return item;
    }

    private Map<String, List<Asset>> index(List<Asset> assets) {
        // MySQL 宽松排序规则可能把全角数字等与 ASCII ID 等同，不能静默忽略返回的记录。
        require(
                assets.stream().allMatch(asset -> validAccountId(asset.accountId())),
                "目标匹配到非标准账户 ID，请人工确认后重新预检");
        return assets.stream().collect(Collectors.groupingBy(Asset::accountId));
    }

    private String encode(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new Conflict("迁移审计序列化失败");
        }
    }

    private <T> T decode(String value, Class<T> type) {
        try {
            return json.readValue(value, type);
        } catch (JsonProcessingException exception) {
            throw new Conflict("迁移审计数据格式错误");
        }
    }

    private String hash(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) throw new Conflict(message);
    }

    /** 可安全返回给操作员的迁移冲突，不含底层数据库异常文本。 */
    public static class Conflict extends RuntimeException {
        public Conflict(String message) {
            super(message);
        }
    }
}
