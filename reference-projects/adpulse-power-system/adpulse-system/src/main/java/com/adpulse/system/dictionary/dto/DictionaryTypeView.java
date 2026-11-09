package com.adpulse.system.dictionary.dto;

import com.adpulse.system.dictionary.model.DictionaryType;
import java.time.LocalDateTime;

/** 字典类型管理视图。 */
public record DictionaryTypeView(
        String id,
        String dictCode,
        String dictName,
        Integer status,
        String remark,
        LocalDateTime createdAt,
        LocalDateTime updatedAt) {

    /** 从持久化模型构造管理视图。 */
    public static DictionaryTypeView from(DictionaryType type) {
        return new DictionaryTypeView(
                type.getId().toString(),
                type.getDictCode(),
                type.getDictName(),
                type.getStatus(),
                type.getRemark(),
                type.getCreatedAt(),
                type.getUpdatedAt());
    }
}
