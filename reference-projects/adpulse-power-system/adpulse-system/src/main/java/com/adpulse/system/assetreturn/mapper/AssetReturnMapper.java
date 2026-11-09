package com.adpulse.system.assetreturn.mapper;

import com.adpulse.system.assetreturn.model.AssetReturn;
import com.adpulse.system.assetreturn.model.ReturnableAsset;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 资产回收单与资产状态的持久化边界。 */
@Mapper
public interface AssetReturnMapper {

    long countReturns(
            @Param("keyword") String keyword,
            @Param("status") String status,
            @Param("assetType") String assetType,
            @Param("assetSubtype") String assetSubtype);

    List<AssetReturn> findReturns(
            @Param("keyword") String keyword,
            @Param("status") String status,
            @Param("assetType") String assetType,
            @Param("assetSubtype") String assetSubtype,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    AssetReturn findReturn(@Param("id") Long id);

    AssetReturn lockReturn(@Param("id") Long id);

    ReturnableAsset lockAsset(@Param("id") Long id);

    int insertReturn(AssetReturn assetReturn);

    int markAssetReturnPending(
            @Param("assetId") Long assetId, @Param("operatorId") Long operatorId);

    int completeReturn(
            @Param("id") Long id,
            @Param("outcome") String outcome,
            @Param("completedById") Long completedById,
            @Param("completedByName") String completedByName);

    int releaseAsset(
            @Param("assetId") Long assetId,
            @Param("assetStatus") String assetStatus,
            @Param("operatorId") Long operatorId);
}
