package com.adpulse.system.user.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 当前登录用户修改密码请求。 */
public record UserPasswordChangeRequest(
        @Size(max = 72) String oldPassword,
        @NotBlank @Size(min = 8, max = 72) String newPassword) {}
