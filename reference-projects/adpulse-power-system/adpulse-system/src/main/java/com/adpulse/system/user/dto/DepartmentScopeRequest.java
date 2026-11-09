package com.adpulse.system.user.dto;

import jakarta.validation.constraints.NotNull;

/** 用户部门数据范围项。 */
public record DepartmentScopeRequest(
        @NotNull Long departmentId, @NotNull Boolean includeChildren) {}
