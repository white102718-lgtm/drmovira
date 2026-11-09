package com.adpulse.system.menu.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** 菜单新增和修改请求。 */
public record MenuSaveRequest(
        @NotNull Long parentId,
        @NotNull @Min(1) @Max(3) Integer menuType,
        @NotBlank @Size(max = 100) String menuCode,
        @NotBlank @Size(max = 100) String menuName,
        @Size(max = 255) String routePath,
        @Size(max = 255) String component,
        @Size(max = 100) String icon,
        @Size(max = 128) String permissionCode,
        @NotNull Integer visible,
        @NotNull Integer cacheable,
        @Size(max = 500) String externalLink,
        Integer sortOrder,
        @NotNull Integer status,
        @Size(max = 500) String remark) {}
