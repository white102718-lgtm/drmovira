package com.adpulse.system.user.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** 通用IP规则保存请求。 */
public record IpRuleSaveRequest(
        @NotBlank @Size(max = 64) String ipCidr,
        @Size(max = 100) String ruleName,
        @NotNull Integer status,
        @Size(max = 500) String remark) {}
