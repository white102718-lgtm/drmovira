package com.adpulse.system.application.dto;

import com.adpulse.system.application.model.ApplicationType;
import java.time.LocalDateTime;

/** 申请类型管理和资源申请中心共用的读取视图。 */
public record ApplicationTypeView(
        String id,
        String typeName,
        String description,
        String icon,
        Integer sortOrder,
        Integer status,
        LocalDateTime updatedAt) {

    /** 将持久化实体转换为前端安全使用的字符串 ID 视图。 */
    public static ApplicationTypeView from(ApplicationType type) {
        return new ApplicationTypeView(
                type.getId().toString(),
                type.getTypeName(),
                type.getDescription(),
                type.getIcon(),
                type.getSortOrder(),
                type.getStatus(),
                type.getUpdatedAt());
    }
}
