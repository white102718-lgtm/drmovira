package com.adpulse.system.application.mapper;

import com.adpulse.system.application.model.ApplicationType;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 申请类型主数据持久化接口。 */
@Mapper
public interface ApplicationTypeMapper {
    List<ApplicationType> findAll(@Param("enabledOnly") boolean enabledOnly);

    ApplicationType findById(@Param("id") Long id);

    int countByName(@Param("typeName") String typeName, @Param("excludeId") Long excludeId);

    int insert(ApplicationType type);

    int update(ApplicationType type);
}
