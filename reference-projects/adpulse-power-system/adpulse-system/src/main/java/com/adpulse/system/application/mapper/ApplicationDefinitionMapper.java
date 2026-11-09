package com.adpulse.system.application.mapper;

import com.adpulse.system.application.model.ApplicationDefinition;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 申请入口定义持久化接口。 */
@Mapper
public interface ApplicationDefinitionMapper {
    List<ApplicationDefinition> findAll(
            @Param("keyword") String keyword,
            @Param("status") Integer status,
            @Param("approvalConfigId") Long approvalConfigId,
            @Param("enabledOnly") boolean enabledOnly,
            @Param("viewerId") Long viewerId);

    ApplicationDefinition findById(@Param("id") Long id);

    int countByCode(@Param("applicationCode") String applicationCode);

    int countByIds(@Param("ids") List<Long> ids);

    int clearApprovalConfig(
            @Param("approvalConfigId") Long approvalConfigId, @Param("updatedBy") Long updatedBy);

    int assignApprovalConfig(
            @Param("approvalConfigId") Long approvalConfigId,
            @Param("ids") List<Long> ids,
            @Param("updatedBy") Long updatedBy);

    int insert(ApplicationDefinition definition);

    int update(ApplicationDefinition definition);

    int softDelete(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);
}
