package com.adpulse.system.department.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** 部门新增和修改请求。 */
public record DepartmentSaveRequest(
        @NotNull Long parentId,
        @NotBlank @Pattern(regexp = "^[A-Z][A-Z0-9_]{1,63}$") String deptCode,
        @NotBlank @Size(max = 100) String deptName,
        Integer sortOrder,
        Long leaderUserId,
        @NotNull Integer status,
        @Size(max = 500) String remark) {}
