package com.adpulse.system.role.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.Set;

/** 角色及菜单权限保存请求。 */
public record RoleSaveRequest(
        @NotBlank(message = "角色编码不能为空") @Size(max = 64, message = "角色编码不能超过64个字符") String roleCode,
        @NotBlank @Size(max = 100) String roleName,
        @NotNull @Min(0) @Max(1) Integer status,
        Integer sortOrder,
        @Size(max = 500) String remark,
        Set<Long> menuIds) {}
