package com.adpulse.system.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 飞书 OAuth 回调登录请求。 */
public record FeishuOAuthCallbackRequest(
        @NotBlank @Size(max = 512) String code, @NotBlank @Size(max = 128) String state) {}
