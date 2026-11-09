package com.adpulse.system.dictionary.dto;

import com.adpulse.system.dictionary.model.DictionaryItem;
import java.time.LocalDateTime;

/** 字典项管理视图。 */
public record DictionaryItemView(
        String id,
        String dictTypeId,
        String value,
        String label,
        Integer sortOrder,
        Integer status,
        String remark,
        LocalDateTime createdAt,
        LocalDateTime updatedAt) {

    /** 从持久化模型构造管理视图。 */
    public static DictionaryItemView from(DictionaryItem item) {
        return new DictionaryItemView(
                item.getId().toString(),
                item.getDictTypeId().toString(),
                item.getItemValue(),
                item.getItemLabel(),
                item.getSortOrder(),
                item.getStatus(),
                item.getRemark(),
                item.getCreatedAt(),
                item.getUpdatedAt());
    }
}
