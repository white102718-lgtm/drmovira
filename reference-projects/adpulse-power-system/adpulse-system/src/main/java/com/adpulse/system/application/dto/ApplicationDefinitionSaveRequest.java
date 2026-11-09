package com.adpulse.system.application.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** 申请入口新增或修改请求。 */
public record ApplicationDefinitionSaveRequest(
        @Pattern(regexp = "^[A-Z][A-Z0-9_]{1,63}$") String applicationCode,
        @NotBlank @Size(max = 100) String applicationName,
        @NotNull Long applicationTypeId,
        @Size(max = 255) String description,
        @NotBlank @Size(max = 64) String icon,
        @NotBlank @Pattern(regexp = "^(all|admins)$") String visibility,
        @NotNull Boolean showInResourceApplication,
        @NotNull @Min(0) @Max(9999) Integer sortOrder,
        @NotNull @Min(0) @Max(1) Integer status) {}
