package com.adpulse.system.user.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.util.Set;

/** 飞书用户本地角色、数据范围及IP规则授权请求。 */
public record UserAuthorizationRequest(
        @NotNull @Min(0) @Max(2) Integer ipAccessMode,
        Set<Long> roleIds,
        Set<DepartmentScopeRequest> departmentScopes,
        Set<String> ipCidrs) {}
