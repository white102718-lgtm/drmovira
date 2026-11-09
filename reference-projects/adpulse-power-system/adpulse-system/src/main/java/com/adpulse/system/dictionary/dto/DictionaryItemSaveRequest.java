package com.adpulse.system.dictionary.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** 字典项保存请求。 */
public record DictionaryItemSaveRequest(
        @NotBlank @Size(max = 100) String value,
        @NotBlank @Size(max = 100) String label,
        Integer sortOrder,
        @NotNull @Min(0) @Max(1) Integer status,
        @Size(max = 500) String remark) {}
