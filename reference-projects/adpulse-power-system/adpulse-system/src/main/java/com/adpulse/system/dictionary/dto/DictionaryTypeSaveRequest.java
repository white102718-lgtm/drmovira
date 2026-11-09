package com.adpulse.system.dictionary.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** 字典类型保存请求。 */
public record DictionaryTypeSaveRequest(
        @NotBlank @Pattern(regexp = "^[A-Z][A-Z0-9_]{1,63}$") String dictCode,
        @NotBlank @Size(max = 100) String dictName,
        @NotNull @Min(0) @Max(1) Integer status,
        @Size(max = 500) String remark) {}
