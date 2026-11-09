package com.adpulse.system.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/** MFA绑定或验证请求。 */
public record MfaCodeRequest(
        @NotBlank(message = "MFA挑战不能为空") String challengeToken,
        @NotBlank(message = "MFA动态码不能为空") @Pattern(regexp = "\\d{6}", message = "MFA动态码必须是6位数字") String totpCode) {}
