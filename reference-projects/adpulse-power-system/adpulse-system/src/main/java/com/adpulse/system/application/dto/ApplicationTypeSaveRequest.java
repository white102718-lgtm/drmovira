package com.adpulse.system.application.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** 申请类型新增或修改请求。 */
public record ApplicationTypeSaveRequest(
        @NotBlank @Size(max = 64) String typeName,
        @Size(max = 255) String description,
        @NotBlank @Size(max = 64) String icon,
        @NotNull @Min(0) @Max(9999) Integer sortOrder,
        @NotNull @Min(0) @Max(1) Integer status) {}
