package com.adpulse.system.dictionary.model;

import com.adpulse.system.common.model.AuditedEntity;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 字典类型持久化模型。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class DictionaryType extends AuditedEntity {
    private String dictCode;
    private String dictName;
    private Integer status;
    private String remark;
}
