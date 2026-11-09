package com.adpulse.main.adaccountasset;

import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAsset;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAssetChangeEvent;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.PageFilter;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 广告账户资产信息主表的 MyBatis 持久化接口。 */
@Mapper
public interface AdAccountAssetMapper {
    /** 查询指定系统字典是否存在启用值，用于缺省开启的业务开关。 */
    int countEnabledDictionaryValue(
            @Param("dictCode") String dictCode, @Param("value") String value);

    /** 批量查询广告账户资产信息。 */
    List<AdAccountAsset> findByAccountIds(@Param("accountIds") List<String> accountIds);

    /** 查询全部有效广告账户资产，用于与 MongoDB 账户集合合并。 */
    List<AdAccountAsset> findAll();

    /** 按列表关键字和主表字段统计有效广告账户资产。 */
    long countPage(@Param("keyword") String keyword, @Param("filter") PageFilter filter);

    /** 按列表关键字和主表字段分页查询有效广告账户资产。 */
    List<AdAccountAsset> findPage(
            @Param("keyword") String keyword,
            @Param("filter") PageFilter filter,
            @Param("offset") long offset,
            @Param("pageSize") int pageSize);

    /** 按列表关键字和主表字段查询全部有效广告账户资产。 */
    List<AdAccountAsset> findAllByFilter(
            @Param("keyword") String keyword, @Param("filter") PageFilter filter);

    /** 按资产主键批量查询有效广告账户。 */
    List<AdAccountAsset> findByIds(@Param("ids") List<Long> ids);

    /** 按渠道名称精准查询广告账户资产。 */
    List<AdAccountAsset> findByChannelName(@Param("channelName") String channelName);

    /** 按账户 ID 查询广告账户资产信息。 */
    AdAccountAsset findByAccountId(@Param("accountId") String accountId);

    /** 按账户 ID 原子新增或覆盖完整资产信息。 */
    int upsert(AdAccountAsset asset);

    /** 飞书同步专用 upsert；人工锁定的已有记录不会被覆盖。 */
    int upsertFromFeishu(AdAccountAsset asset);

    /** MongoDB 同步名称和平台状态，不受人工业务字段锁定影响。 */
    int upsertPlatformSnapshot(AdAccountAsset asset);

    /** 按稳定账户 ID 更新 MongoDB 名称和状态快照，用于安全处理平台改名。 */
    int updatePlatformSnapshotByAccountId(AdAccountAsset asset);

    /** 恢复指定资产的飞书自动同步。 */
    int resetManualUpdate(@Param("accountId") String accountId, @Param("updatedBy") Long updatedBy);

    /** 渠道移除账户时仅解除渠道归属，不删除全局广告账户资产。 */
    int clearChannel(@Param("accountId") String accountId, @Param("updatedBy") Long updatedBy);

    /** 更新广告账户库存状态；使用人关系由业务服务在同一事务内维护。 */
    int updateInventoryStatus(
            @Param("assetId") Long assetId,
            @Param("inventoryStatus") String inventoryStatus,
            @Param("updatedBy") Long updatedBy);

    /** 删除账户类型配置时，将新台账中的引用归为未分类。 */
    int detachAccountType(
            @Param("accountType") String accountType, @Param("updatedBy") Long updatedBy);

    /** 写入一条不可变的广告账户资料更新审计事件。 */
    int insertChangeEvent(AdAccountAssetChangeEvent event);

    /** 查询指定广告账户资产的资料更新审计事件。 */
    List<AdAccountAssetChangeEvent> findChangeEventsByAssetId(
            @Param("adAccountAssetId") Long adAccountAssetId);

    /** 判断指定资产是否已经持久化某类生命周期事件。 */
    int countChangeEventsByAssetIdAndType(
            @Param("adAccountAssetId") Long adAccountAssetId, @Param("eventType") String eventType);

    /** 写入当前操作人的广告账户导入记录。 */
    int insertImportLog(AdAccountImportLog importLog);

    /** 查询当前操作人的广告账户导入记录。 */
    List<AdAccountImportLog> findImportLogsByOperatorId(@Param("operatorId") Long operatorId);

    /** 按记录与操作人查询，防止跨用户下载失败文件。 */
    AdAccountImportLog findImportLogByIdAndOperatorId(
            @Param("id") Long id, @Param("operatorId") Long operatorId);
}
