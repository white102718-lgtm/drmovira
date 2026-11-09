package com.adpulse.system.user.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.Set;

/** 用户及其角色、部门范围和个人IP规则保存请求。 */
public record UserSaveRequest(
        @NotBlank @Pattern(regexp = "^(?:1[3-9]\\d{9}|\\+[1-9]\\d{7,14})$", message = "请输入正确的国际手机号")
                String phone,
        @Size(min = 8, max = 72) String password,
        @NotBlank @Size(max = 100) String displayName,
        @Size(max = 64) String englishNickname,
        @Size(max = 100) String realName,
        Long primaryDepartmentId,
        @Email @Size(max = 128) String email,
        @Size(max = 500) String avatarUrl,
        @NotNull @Min(0) @Max(1) Integer status,
        @NotNull @Min(0) @Max(2) Integer ipAccessMode,
        @Size(max = 500) String remark,
        Set<Long> roleIds,
        Set<DepartmentScopeRequest> departmentScopes,
        Set<String> ipCidrs) {}
