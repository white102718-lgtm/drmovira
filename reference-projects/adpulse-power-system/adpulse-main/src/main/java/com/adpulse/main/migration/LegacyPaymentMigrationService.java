package com.adpulse.main.migration;

import static com.adpulse.main.migration.AssetMigrationService.require;

import com.adpulse.main.manualtask.ManualTaskContext;
import com.adpulse.main.migration.AssetMigrationModels.ChannelSnapshot;
import com.adpulse.main.migration.AssetMigrationModels.Identity;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.Candidate;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.ExistingApplication;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.Ledger;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.LegacyPayment;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.PaymentDefinition;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.TargetChannel;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.TargetUser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.math.BigDecimal;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 旧系统打款申请预检、历史快照转换及幂等写入服务。 */
@Service
@ConditionalOnProperty(name = "adpulse.asset-migration.enabled", havingValue = "true")
public class LegacyPaymentMigrationService {
    private static final Set<Integer> MIGRATABLE_STATUSES = Set.of(1, 2);
    private static final int BLOCKER_LOG_LIMIT = 100;
    private static final String DEPARTED_REQUESTER_NAME = "邹丹梅";
    private static final String DEPARTED_REQUESTER_CC_NAME = "陈艳霞";

    private final LegacyAssetReader reader;
    private final LegacyPaymentMigrationMapper mapper;
    private final AssetMigrationMapper assetMapper;
    private final AssetMigrationProperties properties;
    private final ChannelMigrationMappingResolver channelMappings;
    private final ObjectMapper json;

    public LegacyPaymentMigrationService(
            LegacyAssetReader reader,
            LegacyPaymentMigrationMapper mapper,
            AssetMigrationMapper assetMapper,
            AssetMigrationProperties properties,
            ChannelMigrationMappingResolver channelMappings,
            ObjectMapper json) {
        this.reader = reader;
        this.mapper = mapper;
        this.assetMapper = assetMapper;
        this.properties = properties;
        this.channelMappings = channelMappings;
        this.json = json;
    }

    /** 预检不写业务数据，但必须允许手动任务日志更新执行记录。 */
    @Transactional
    public void preview(ManualTaskContext context) {
        Preview plan = buildPreview();
        logPreview(context, plan);
    }

    /** 在同一目标库事务内重新预检并写入所有可迁移记录。 */
    @Transactional
    public void apply(ManualTaskContext context) {
        Preview plan = buildPreview();
        logPreview(context, plan);
        if (plan.candidates().isEmpty()) {
            context.log().info("没有新的可迁移记录，本次未写入数据");
            return;
        }
        for (Candidate candidate : plan.candidates()) {
            require(mapper.insertApplication(candidate) == 1, "历史申请写入失败");
            insertLogs(candidate);
            require(
                    mapper.insertLedger(
                                    properties.getTargetEnvironment().name(),
                                    properties.getSourceUuid(),
                                    properties.getSourceSchema(),
                                    properties.getTargetUuid(),
                                    properties.getTargetSchema(),
                                    candidate,
                                    context.executionId(),
                                    context.operatorId())
                            == 1,
                    "迁移账本写入失败");
        }
        context.log().info("迁移事务已提交，新增历史打款申请：" + plan.candidates().size() + " 条");
    }

    private Preview buildPreview() {
        properties.validateEnvironment();
        require(mapper.schemaReady() == 1, "打款迁移数据库脚本尚未应用");
        Identity target = assetMapper.identity();
        require(
                properties.getTargetUuid().equals(target.serverUuid())
                        && properties.getTargetSchema().equals(target.schemaName()),
                "目标数据库实例或库名与迁移配置不符");

        List<LegacyPayment> payments = reader.readPayments();
        ChannelSnapshot channelSnapshot = channelMappings.resolve();
        PaymentDefinition definition = mapper.paymentDefinition();
        require(definition != null, "当前环境没有启用的 PAYMENT 申请定义和审批配置");

        Map<String, List<TargetUser>> usersByDisplayName =
                usersByDisplayName(mapper.migrationUsers());
        Map<Long, TargetChannel> channels =
                targetChannels(payments, channelSnapshot.ids()).stream()
                        .collect(Collectors.toMap(TargetChannel::id, value -> value));
        Map<Long, Ledger> ledgers =
                mapper
                        .ledgers(
                                properties.getTargetEnvironment().name(),
                                properties.getSourceUuid(),
                                properties.getSourceSchema(),
                                properties.getTargetUuid(),
                                properties.getTargetSchema())
                        .stream()
                        .collect(Collectors.toMap(Ledger::sourcePaymentId, value -> value));

        Map<Integer, StatusSummary> statuses = new LinkedHashMap<>();
        List<Candidate> candidates = new ArrayList<>();
        List<String> blockers = new ArrayList<>();
        int alreadyMigrated = 0;
        int conflicts = 0;
        int userBlocked = 0;
        int channelBlocked = 0;
        int fieldBlocked = 0;
        int skipped = 0;
        for (LegacyPayment source : payments) {
            StatusSummary summary =
                    statuses.computeIfAbsent(source.auditStatus(), ignored -> new StatusSummary());
            summary.count++;
            summary.amount = summary.amount.add(zero(source.amount()));
            if (!MIGRATABLE_STATUSES.contains(source.auditStatus())) {
                skipped++;
                continue;
            }
            String sourceHash = hash(source);
            Ledger ledger = ledgers.get(source.sourceId());
            if (ledger != null) {
                ExistingApplication application =
                        mapper.applicationByNo(applicationNo(source.sourceId()));
                if (sourceHash.equals(ledger.sourceHash())
                        && application != null
                        && Objects.equals(application.id(), ledger.targetApplicationId())) {
                    alreadyMigrated++;
                } else {
                    conflicts++;
                    blockers.add(blocker(source, "迁移账本或目标申请与当前来源摘要不一致"));
                }
                continue;
            }
            if (mapper.applicationByNo(applicationNo(source.sourceId())) != null) {
                conflicts++;
                blockers.add(blocker(source, "目标申请号已存在但没有对应迁移账本"));
                continue;
            }
            String validation = validateSource(source);
            if (validation != null) {
                fieldBlocked++;
                blockers.add(blocker(source, validation));
                continue;
            }
            TargetUser requester = uniqueUser(usersByDisplayName, source.requesterName());
            if (requester == null) {
                userBlocked++;
                blockers.add(blocker(source, "申请人姓名无法唯一匹配：" + displayName(source.requesterName())));
                continue;
            }
            TargetUser auditor = uniqueUser(usersByDisplayName, source.auditorName());
            if (auditor == null) {
                userBlocked++;
                blockers.add(blocker(source, "审核人姓名无法唯一匹配：" + displayName(source.auditorName())));
                continue;
            }
            TargetUser ccUser = null;
            if (DEPARTED_REQUESTER_NAME.equals(normalizeName(source.requesterName()))) {
                ccUser = uniqueActiveUser(usersByDisplayName, DEPARTED_REQUESTER_CC_NAME);
                if (ccUser == null) {
                    userBlocked++;
                    blockers.add(blocker(source, "抄送人姓名无法唯一匹配启用用户：" + DEPARTED_REQUESTER_CC_NAME));
                    continue;
                }
            }
            Long targetChannelId = channelSnapshot.ids().get(source.sourceChannelId());
            TargetChannel channel = targetChannelId == null ? null : channels.get(targetChannelId);
            if (channel == null) {
                channelBlocked++;
                blockers.add(blocker(source, "渠道缺少有效迁移映射"));
                continue;
            }
            candidates.add(
                    candidate(source, sourceHash, requester, auditor, ccUser, channel, definition));
        }
        return new Preview(
                statuses,
                candidates,
                blockers,
                alreadyMigrated,
                conflicts,
                userBlocked,
                channelBlocked,
                fieldBlocked,
                skipped,
                payments.size());
    }

    private Candidate candidate(
            LegacyPayment source,
            String sourceHash,
            TargetUser requester,
            TargetUser auditor,
            TargetUser ccUser,
            TargetChannel channel,
            PaymentDefinition definition) {
        Candidate value = new Candidate();
        value.setSource(source);
        value.setRequester(requester);
        value.setAuditor(auditor);
        value.setRequesterName(limit(requester.snapshotName(), 64));
        value.setAuditorName(limit(auditor.snapshotName(), 64));
        value.setChannel(channel);
        value.setDefinition(definition);
        value.setApplicationNo(applicationNo(source.sourceId()));
        value.setTargetStatus(source.auditStatus() == 1 ? "APPROVED" : "REJECTED");
        value.setSourceHash(sourceHash);

        NodeSnapshot node = nodeSnapshot(definition.nodes());
        value.setCurrentNodeIndex(source.auditStatus() == 1 ? node.lastIndex() : 0);
        value.setApprovalNodeName(node.approvalName());
        value.setHandlerNodeName(node.handlerName());
        value.setFormData(formData(source, requester, auditor, ccUser, channel, definition));
        value.setCompletionData(completionData(source));
        return value;
    }

    private void insertLogs(Candidate candidate) {
        LegacyPayment source = candidate.getSource();
        mapper.insertLog(
                candidate.getTargetApplicationId(),
                "SUBMITTED",
                candidate.getRequester().id(),
                candidate.getRequesterName(),
                "旧系统提交申请",
                null,
                0,
                "提交申请",
                source.createdAt());
        if (source.auditStatus() == 2) {
            mapper.insertLog(
                    candidate.getTargetApplicationId(),
                    "REJECTED",
                    candidate.getAuditor().id(),
                    candidate.getAuditorName(),
                    limit(blankToNull(source.rejectReason()), 1000),
                    null,
                    0,
                    candidate.getApprovalNodeName(),
                    source.auditTime());
            return;
        }
        mapper.insertLog(
                candidate.getTargetApplicationId(),
                "APPROVED",
                candidate.getAuditor().id(),
                candidate.getAuditorName(),
                "旧系统审核通过",
                null,
                0,
                candidate.getApprovalNodeName(),
                source.auditTime());
        mapper.insertLog(
                candidate.getTargetApplicationId(),
                "COMPLETED",
                candidate.getAuditor().id(),
                candidate.getAuditorName(),
                "旧系统打款完成",
                candidate.getCompletionData(),
                candidate.getCurrentNodeIndex(),
                candidate.getHandlerNodeName(),
                source.auditTime());
    }

    private String formData(
            LegacyPayment source,
            TargetUser requester,
            TargetUser auditor,
            TargetUser ccUser,
            TargetChannel channel,
            PaymentDefinition definition) {
        ObjectNode form = json.createObjectNode();
        form.put("applicationDefinitionId", String.valueOf(definition.definitionId()));
        form.put("applicationCode", "PAYMENT");
        form.put("applicationName", definition.applicationName());
        form.put("channelId", String.valueOf(channel.id()));
        form.put("channelName", channel.channelName());
        putDecimal(form, "amount", source.amount());
        putDecimal(form, "channelYesterdayCost", source.channelYesterdayCost());
        putText(form, "paymentAddress", source.paymentAddress());
        putText(form, "remark", source.remark());
        if (requester.departmentId() != null) {
            form.put("_requesterDepartmentId", String.valueOf(requester.departmentId()));
        }
        putText(form, "_requesterDepartmentName", requester.departmentName());
        if (ccUser != null) {
            form.put("_ccUserIds", String.valueOf(ccUser.id()));
        }

        ObjectNode legacy = form.putObject("_legacy");
        legacy.put("sourceSystem", "MPOWER");
        legacy.put("userMatchStrategy", "TENANT_0_DISPLAY_NAME");
        legacy.put("sourcePaymentId", String.valueOf(source.sourceId()));
        putText(legacy, "orderNo", source.orderNo());
        legacy.put("auditStatus", source.auditStatus());
        legacy.put("sourceType", source.sourceType());
        putText(legacy, "comment", source.comment());
        putText(legacy, "receiptUrl", source.receiptUrl());
        legacy.put("hasReceipt", Objects.equals(source.hasReceipt(), 1));
        putText(legacy, "feishuCardId", source.feishuCardId());
        if (source.feishuNoticeStatus() != null) {
            legacy.put("feishuNoticeStatus", source.feishuNoticeStatus());
        }
        legacy.put("sourceRequesterId", String.valueOf(source.requesterSourceId()));
        putText(legacy, "sourceRequesterName", source.requesterName());
        legacy.put("sourceRequesterTenantId", source.requesterTenantId());
        legacy.put("targetRequesterId", String.valueOf(requester.id()));
        legacy.put("sourceAuditorId", String.valueOf(source.auditorSourceId()));
        putText(legacy, "sourceAuditorName", source.auditorName());
        legacy.put("sourceAuditorTenantId", source.auditorTenantId());
        legacy.put("targetAuditorId", String.valueOf(auditor.id()));
        if (ccUser != null) {
            legacy.put("ccOverrideSourceRequesterName", DEPARTED_REQUESTER_NAME);
            legacy.put("ccOverrideTargetName", DEPARTED_REQUESTER_CC_NAME);
            legacy.put("ccOverrideTargetUserId", String.valueOf(ccUser.id()));
        }
        legacy.put("sourceChannelId", String.valueOf(source.sourceChannelId()));
        putText(legacy, "sourceDepartmentName", source.sourceDepartmentName());
        legacy.put("migrationEnvironment", properties.getTargetEnvironment().name());
        return write(form);
    }

    private String completionData(LegacyPayment source) {
        if (source.auditStatus() != 1) return null;
        ObjectNode data = json.createObjectNode();
        putDecimal(data, "actualAmount", source.actualAmount());
        ObjectNode legacy = data.putObject("_legacy");
        putText(legacy, "receiptUrl", source.receiptUrl());
        legacy.put("hasReceipt", Objects.equals(source.hasReceipt(), 1));
        return write(data);
    }

    private NodeSnapshot nodeSnapshot(String nodesJson) {
        try {
            JsonNode nodes = json.readTree(nodesJson);
            require(nodes != null && nodes.isArray() && !nodes.isEmpty(), "PAYMENT 审批节点配置为空");
            int lastIndex = nodes.size() - 1;
            String approvalName = "业务审批";
            for (JsonNode node : nodes) {
                if ("approval".equals(node.path("kind").asText())) {
                    approvalName = node.path("name").asText(approvalName);
                    break;
                }
            }
            String handlerName = nodes.get(lastIndex).path("name").asText("业务办理");
            return new NodeSnapshot(lastIndex, approvalName, handlerName);
        } catch (JsonProcessingException exception) {
            throw new AssetMigrationService.Conflict("PAYMENT 审批节点配置不是有效 JSON");
        }
    }

    private List<TargetChannel> targetChannels(
            List<LegacyPayment> payments, Map<Long, Long> mappings) {
        List<Long> ids =
                payments.stream()
                        .map(LegacyPayment::sourceChannelId)
                        .filter(Objects::nonNull)
                        .map(mappings::get)
                        .filter(Objects::nonNull)
                        .distinct()
                        .sorted()
                        .toList();
        return ids.isEmpty() ? List.of() : mapper.activeChannels(ids);
    }

    static Map<String, List<TargetUser>> usersByDisplayName(List<TargetUser> users) {
        return users.stream()
                .filter(user -> normalizeName(user.displayName()) != null)
                .collect(Collectors.groupingBy(user -> normalizeName(user.displayName())));
    }

    static TargetUser uniqueUser(Map<String, List<TargetUser>> users, String name) {
        String normalized = normalizeName(name);
        if (normalized == null) return null;
        List<TargetUser> matches = users.getOrDefault(normalized, List.of());
        return matches.size() == 1 ? matches.get(0) : null;
    }

    static TargetUser uniqueActiveUser(Map<String, List<TargetUser>> users, String name) {
        String normalized = normalizeName(name);
        if (normalized == null) return null;
        List<TargetUser> matches =
                users.getOrDefault(normalized, List.of()).stream()
                        .filter(user -> Objects.equals(user.status(), 1))
                        .toList();
        return matches.size() == 1 ? matches.get(0) : null;
    }

    private String validateSource(LegacyPayment source) {
        if (source.sourceId() == null) return "来源申请 ID 为空";
        if (source.requesterSourceId() == null) return "来源申请人 ID 为空";
        if (!Objects.equals(source.requesterTenantId(), 0L)) {
            return "来源申请人不是 tenant_id=0 的管理端用户";
        }
        if (normalizeName(source.requesterName()) == null) return "来源申请人姓名为空";
        if (source.auditorSourceId() == null) return "来源审核人 ID 为空";
        if (!Objects.equals(source.auditorTenantId(), 0L)) {
            return "来源审核人不是 tenant_id=0 的管理端用户";
        }
        if (normalizeName(source.auditorName()) == null) return "来源审核人姓名为空";
        if (source.sourceChannelId() == null) return "来源渠道 ID 为空";
        if (source.createdAt() == null || source.auditTime() == null) return "创建或审核时间为空";
        if (source.amount() == null || source.amount().compareTo(BigDecimal.ZERO) <= 0) {
            return "申请金额必须大于 0";
        }
        if (source.channelYesterdayCost() == null
                || source.channelYesterdayCost().compareTo(BigDecimal.ZERO) < 0) {
            return "渠道昨日消耗为空或小于 0";
        }
        if (source.paymentAddress() == null || source.paymentAddress().isBlank()) {
            return "打款地址为空";
        }
        if (source.auditStatus() == 1
                && (source.actualAmount() == null
                        || source.actualAmount().compareTo(BigDecimal.ZERO) <= 0)) {
            return "已通过记录的实际打款金额必须大于 0";
        }
        return null;
    }

    private void logPreview(ManualTaskContext context, Preview preview) {
        context.log().info("目标环境：" + properties.getTargetEnvironment().name());
        preview.statuses().entrySet().stream()
                .sorted(
                        Comparator.comparingInt(
                                entry -> entry.getKey() == null ? -1 : entry.getKey()))
                .forEach(
                        entry ->
                                context.log()
                                        .info(
                                                "旧状态 "
                                                        + entry.getKey()
                                                        + "："
                                                        + entry.getValue().count
                                                        + " 条，申请金额合计 "
                                                        + entry.getValue().amount.toPlainString()));
        context.log()
                .info(
                        "预检汇总：来源 "
                                + preview.sourceCount()
                                + "，可迁移 "
                                + preview.candidates().size()
                                + "，已迁移 "
                                + preview.alreadyMigrated()
                                + "，冲突 "
                                + preview.conflicts()
                                + "，人员阻断 "
                                + preview.userBlocked()
                                + "，渠道阻断 "
                                + preview.channelBlocked()
                                + "，字段阻断 "
                                + preview.fieldBlocked()
                                + "，状态跳过 "
                                + preview.skipped());
        preview.blockers().stream()
                .limit(BLOCKER_LOG_LIMIT)
                .forEach(message -> context.log().warn(message));
        if (preview.blockers().size() > BLOCKER_LOG_LIMIT) {
            context.log()
                    .warn("其余阻断记录未逐条输出：" + (preview.blockers().size() - BLOCKER_LOG_LIMIT) + " 条");
        }
    }

    private String hash(LegacyPayment source) {
        try {
            byte[] bytes = json.writeValueAsBytes(source);
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (JsonProcessingException | NoSuchAlgorithmException exception) {
            throw new IllegalStateException("来源记录摘要生成失败", exception);
        }
    }

    private String write(JsonNode value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("迁移快照序列化失败", exception);
        }
    }

    private static String applicationNo(long sourceId) {
        return "LEGACY-PAY-" + sourceId;
    }

    private static String blocker(LegacyPayment source, String reason) {
        return "阻断：旧申请ID="
                + source.sourceId()
                + "，单号="
                + Objects.toString(source.orderNo(), "-")
                + "，原因="
                + reason;
    }

    static String normalizeName(String value) {
        if (value == null) return null;
        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private static String displayName(String value) {
        String normalized = normalizeName(value);
        return normalized == null ? "未提供姓名" : normalized;
    }

    private static BigDecimal zero(BigDecimal value) {
        return value == null ? BigDecimal.ZERO : value;
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    private static String limit(String value, int maxLength) {
        return value == null || value.length() <= maxLength ? value : value.substring(0, maxLength);
    }

    private static void putText(ObjectNode node, String key, String value) {
        if (value == null) node.putNull(key);
        else node.put(key, value);
    }

    private static void putDecimal(ObjectNode node, String key, BigDecimal value) {
        if (value == null) node.putNull(key);
        else node.put(key, value);
    }

    private record NodeSnapshot(int lastIndex, String approvalName, String handlerName) {}

    private static final class StatusSummary {
        private int count;
        private BigDecimal amount = BigDecimal.ZERO;
    }

    private record Preview(
            Map<Integer, StatusSummary> statuses,
            List<Candidate> candidates,
            List<String> blockers,
            int alreadyMigrated,
            int conflicts,
            int userBlocked,
            int channelBlocked,
            int fieldBlocked,
            int skipped,
            int sourceCount) {}
}
