package com.adpulse.main.adaccountasset;

import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAssetAssignment;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 广告账户使用人分配关系持久化接口。 */
@Mapper
public interface AdAccountAssetAssignmentMapper {
    /** 批量查询广告账户当前有效的使用人关系。 */
    List<AdAccountAssetAssignment> findActiveByAssetIds(@Param("assetIds") List<Long> assetIds);

    /** 查询账户全部分配记录，包含已释放关系，用于生命周期使用区间。 */
    List<AdAccountAssetAssignment> findHistoryByAssetId(@Param("assetId") Long assetId);

    /** 查询指定用户当前被分配的广告账户资产 ID。 */
    List<Long> findActiveAssetIdsByUserId(@Param("userId") Long userId);

    /** 幂等创建或恢复使用人关系。 */
    int upsert(AdAccountAssetAssignment assignment);

    /** 解除指定广告账户和用户的使用关系，并保留历史时间。 */
    int release(
            @Param("assetId") Long assetId,
            @Param("userId") Long userId,
            @Param("updatedBy") Long updatedBy,
            @Param("deletedAt") long deletedAt);
}
