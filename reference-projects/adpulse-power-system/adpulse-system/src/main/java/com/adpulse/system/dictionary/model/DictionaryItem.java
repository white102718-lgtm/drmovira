package com.adpulse.system.dictionary.model;

import com.adpulse.system.common.model.AuditedEntity;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 字典项持久化模型。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class DictionaryItem extends AuditedEntity {
    private Long dictTypeId;
    private String itemValue;
    private String itemLabel;
    private Integer sortOrder;
    private Integer status;
    private String remark;
}
