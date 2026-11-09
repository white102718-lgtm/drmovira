package com.adpulse.system.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/** 登录请求。 */
public record LoginRequest(
        @NotBlank(message = "手机号不能为空") @Pattern(regexp = "^(?:1[3-9]\\d{9}|\\+[1-9]\\d{7,14})$", message = "请输入正确的手机号")
                String phone,
        @NotBlank(message = "密码不能为空") String password) {}
