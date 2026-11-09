package com.adpulse.main.migration;

import com.adpulse.main.migration.AssetMigrationModels.*;
import com.adpulse.main.migration.ChannelIncrementModels.*;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 目标库迁移暂存、审计与严格五字段写入。 */
@Mapper
public interface AssetMigrationMapper {
    /** 集群内串行化迁移任务及状态变更。 */
    int lockMutex();

    /** 校验目标数据库身份。 */
    Identity identity();

    /** 确认执行人仍是有效用户。 */
    int activeOperator(long operatorId);

    /** 核对新增所依赖的默认值与事务表引擎。 */
    int schemaReady();

    /** 检查已应用渠道迁移账本是否存在。 */
    int ledgerExists(@Param("environment") String environment);

    /** 获取已提交的老渠道到新渠道映射。 */
    ChannelLedger channelLedger(
            @Param("environment") String environment, @Param("batchKey") String batchKey);

    /** 只查询源渠道 ID 到目标渠道 ID，不缓存费率或渠道其他资料。 */
    String channelMapping(
            @Param("environment") String environment, @Param("batchKey") String batchKey);

    /** 检查增量批次与映射表是否已由管理员初始化。 */
    int channelIncrementSchemaReady();

    /** 检查渠道编码可空及渠道/费率事务引擎。 */
    int channelWriteSchemaReady();

    /** 同一操作员对同一计划和选择重复提交时，返回已提交结果。 */
    ExecuteResult appliedChannelIncrement(
            @Param("environment") String environment,
            @Param("sourceUuid") String sourceUuid,
            @Param("targetUuid") String targetUuid,
            @Param("sourceSchema") String sourceSchema,
            @Param("targetSchema") String targetSchema,
            @Param("operatorId") long operatorId,
            @Param("planHash") String planHash,
            @Param("selectedJson") String selectedJson);

    /** 读取当前环境和实例下所有已应用的增量映射。 */
    List<ExistingMapping> incrementalMappings(
            @Param("environment") String environment,
            @Param("sourceUuid") String sourceUuid,
            @Param("sourceSchema") String sourceSchema,
            @Param("targetUuid") String targetUuid,
            @Param("targetSchema") String targetSchema);

    /** 按目标排序规则检查有效渠道名称或编码冲突。 */
    TargetConflict channelConflict(
            @Param("channelName") String channelName, @Param("channelCode") String channelCode);

    /** 新增来源渠道并回填目标主键。 */
    int insertIncrementChannel(
            @Param("candidate") AppliedChannel candidate, @Param("operatorId") long operatorId);

    /** 新增所选渠道的历史费率。 */
    int insertIncrementRate(
            @Param("targetChannelId") long targetChannelId,
            @Param("rate") LegacyRate rate,
            @Param("operatorId") long operatorId);

    /** 保存不可变的来源渠道到目标渠道映射。 */
    int insertIncrementMapping(
            @Param("environment") String environment,
            @Param("sourceUuid") String sourceUuid,
            @Param("sourceSchema") String sourceSchema,
            @Param("targetUuid") String targetUuid,
            @Param("targetSchema") String targetSchema,
            @Param("sourceChannelId") long sourceChannelId,
            @Param("targetChannelId") long targetChannelId,
            @Param("batchKey") String batchKey,
            @Param("operatorId") long operatorId);

    /** 保存本次已应用增量批次的环境指纹和预检快照。 */
    int insertIncrementBatch(
            @Param("batchKey") String batchKey,
            @Param("environment") String environment,
            @Param("planHash") String planHash,
            @Param("sourceUuid") String sourceUuid,
            @Param("sourceSchema") String sourceSchema,
            @Param("targetUuid") String targetUuid,
            @Param("targetSchema") String targetSchema,
            @Param("planJson") String planJson,
            @Param("operatorId") long operatorId);

    /** 查询有效渠道，执行阶段锁定防止迁移中改名或删除。 */
    List<Channel> channels(@Param("lock") boolean lock);

    /** 读取可用的属性配置。 */
    List<String> attributes();

    /** 创建排队任务。 */
    void insertJob(Job job);

    /** 读取任务。 */
    Job job(String id);

    /** 当前操作员最近的账户迁移任务，用于刷新页面后恢复进度。 */
    List<Job> recentJobs(long operatorId);

    /** 返回下一项可执行任务。 */
    Job nextJob();

    /** 持久化状态与审计计数。 */
    void saveJob(Job job);

    /** 批量保存不可变计划。 */
    void insertItems(@Param("items") List<Item> items);

    /** 分页读取计划明细。 */
    List<Item> items(
            @Param("jobId") String jobId,
            @Param("afterId") long afterId,
            @Param("state") String state);

    /** 查找所有活跃匹配项，不能使用 LIMIT 1 掩盖重复。 */
    List<Asset> assets(@Param("accountIds") List<String> accountIds, @Param("lock") boolean lock);

    /** 只更新五字段中的渠道与账户类型、属性；账户 ID 用于稳定匹配。 */
    int updateAssets(@Param("items") List<Item> items);

    /** 批量新增资产，其他业务字段使用表默认值。 */
    int insertAssets(@Param("items") List<Item> items, @Param("operatorId") long operatorId);

    /** 保存本批执行后镜像，与资产写入处于同一事务。 */
    void finishItems(@Param("items") List<Item> items);
}
