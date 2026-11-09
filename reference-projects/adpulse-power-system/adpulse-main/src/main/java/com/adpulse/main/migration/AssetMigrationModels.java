package com.adpulse.main.migration;

import java.util.List;
import lombok.Data;

/** 渠道账户迁移的来源、计划及审计模型，只包含迁移需要的字段。 */
public final class AssetMigrationModels {
    private AssetMigrationModels() {}

    /** 直接从当前目标库读取的账本状态和内容指纹。 */
    public record ChannelLedger(
            String sourceFingerprint,
            String targetFingerprint,
            String payloadHash,
            String mappingHash) {}

    /** 由当前环境账本解析的只读映射及环境绑定版本。 */
    public record ChannelSnapshot(String version, java.util.Map<Long, Long> ids) {}

    /** 当前服务配置与已核对的目标环境，不包含连接凭据。 */
    public record EnvironmentView(
            String targetEnvironment,
            String sourceUuid,
            String sourceSchema,
            String targetUuid,
            String targetSchema,
            String channelLedgerTable,
            String channelBatchKey,
            boolean mappingCacheEnabled) {}

    /** 老系统内部账户主键与广告平台账户 ID 必须分别保存。 */
    public record Source(
            long sourceId,
            Long channelId,
            String accountId,
            String accountType,
            Integer attribute,
            long tenantId) {}

    /** 数据库实例身份。 */
    public record Identity(String serverUuid, String schemaName) {}

    /** 已迁移渠道的有效名称；不进行 trim。 */
    public record Channel(long id, String channelName) {}

    /** 五个业务字段。 */
    public record Values(
            String accountId,
            Long channelId,
            String channelName,
            String accountType,
            String accountAttribute) {}

    /** 目标前镜像；不读取 BM、卡号等无关字段。 */
    public record Asset(
            long id,
            String accountId,
            Long channelId,
            String channelName,
            String accountType,
            String accountAttribute,
            int manual,
            String updatedAt) {
        Values values() {
            return new Values(accountId, channelId, channelName, accountType, accountAttribute);
        }
    }

    /** 预检结果及执行进度，JSON 中使用字符串任务 ID。 */
    @Data
    public static class Job {
        private String id;
        private String state;
        private String planHash;
        private String sourceHash;
        private String channelHash;
        private long operatorId;
        private int sourceCount;
        private int total;
        private int completed;
        private int isolated;
        private int duplicates;
        private String error;
    }

    /** 持久化的单账户计划，同时保存原始来源记录和执行前后镜像。 */
    @Data
    public static class Item {
        private long id;
        private String jobId;
        private String accountId;
        private Long targetId;
        private String action;
        private String state;
        private String reason;
        private String sourceJson;
        private String beforeJson;
        private String desiredJson;
        private String afterJson;
    }

    /** 执行已审阅的计划，显式接受默认库存与后续自动同步行为。 */
    public record Execute(
            String planHash, boolean acceptAvailableInventory, boolean acceptAutomaticSync) {}

    /** 分页查询结果。 */
    public record Items(List<ItemView> items, String nextAfterId) {}

    /** HTTP 任务视图，不暴露持久化实体或内部快照哈希。 */
    public record JobView(
            String id,
            String state,
            String planHash,
            String operatorId,
            int sourceCount,
            int total,
            int completed,
            int isolated,
            int duplicates,
            String error) {
        static JobView of(Job job) {
            return new JobView(
                    job.getId(),
                    job.getState(),
                    job.getPlanHash(),
                    Long.toString(job.getOperatorId()),
                    job.getSourceCount(),
                    job.getTotal(),
                    job.getCompleted(),
                    job.getIsolated(),
                    job.getDuplicates(),
                    job.getError());
        }
    }

    /** HTTP 明细视图，所有主键按字符串返回，镜像均只含迁移所需字段。 */
    public record ItemView(
            String id,
            String accountId,
            String targetId,
            String action,
            String state,
            String reason,
            String sourceJson,
            String beforeJson,
            String desiredJson,
            String afterJson) {
        static ItemView of(Item item) {
            return new ItemView(
                    Long.toString(item.getId()),
                    item.getAccountId(),
                    item.getTargetId() == null ? null : item.getTargetId().toString(),
                    item.getAction(),
                    item.getState(),
                    item.getReason(),
                    item.getSourceJson(),
                    item.getBeforeJson(),
                    item.getDesiredJson(),
                    item.getAfterJson());
        }
    }
}
