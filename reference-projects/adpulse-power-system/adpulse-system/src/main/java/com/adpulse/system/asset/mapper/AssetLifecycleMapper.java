package com.adpulse.system.asset.mapper;

import com.adpulse.system.asset.model.MediaAssetLifecycleEvent;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 资产生命周期事件的持久化接口。 */
@Mapper
public interface AssetLifecycleMapper {
    int insert(MediaAssetLifecycleEvent event);

    List<MediaAssetLifecycleEvent> findByAssetId(@Param("assetId") Long assetId);
}
