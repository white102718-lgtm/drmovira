package com.adpulse.system.user.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 管理员重置用户密码请求。 */
public record PasswordResetRequest(@NotBlank @Size(min = 8, max = 72) String newPassword) {}
