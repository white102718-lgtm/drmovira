package com.adpulse.system.user.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 当前登录用户修改个人资料的请求。 */
public record UserProfileUpdateRequest(
        @NotBlank @Size(max = 100) String displayName,
        @Size(max = 64) String englishNickname,
        @Size(max = 100) String realName,
        @Email @Size(max = 128) String email,
        @Size(max = 500) String avatarUrl) {}
