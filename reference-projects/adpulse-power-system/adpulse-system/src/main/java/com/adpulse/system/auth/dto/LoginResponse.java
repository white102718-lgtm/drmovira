package com.adpulse.system.auth.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;
import java.util.Set;

/** 系统认证后的成功、MFA绑定或MFA验证阶段响应。 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record LoginResponse(
        String loginStatus,
        String challengeToken,
        Long challengeExpiresInSeconds,
        String mfaSecret,
        String otpAuthUri,
        String accessToken,
        String tokenType,
        Long expiresInSeconds,
        String userId,
        String displayName,
        Set<String> permissions,
        Instant issuedAt) {

    /** 创建首次MFA绑定阶段响应。 */
    public static LoginResponse bindRequired(
            String challengeToken, long expiresInSeconds, String secret, String otpAuthUri) {
        return new LoginResponse(
                "MFA_BIND_REQUIRED",
                challengeToken,
                expiresInSeconds,
                secret,
                otpAuthUri,
                null,
                null,
                null,
                null,
                null,
                null,
                null);
    }

    /** 创建已绑定用户的MFA验证阶段响应。 */
    public static LoginResponse verifyRequired(String challengeToken, long expiresInSeconds) {
        return new LoginResponse(
                "MFA_VERIFY_REQUIRED",
                challengeToken,
                expiresInSeconds,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null);
    }

    /** 创建完整认证成功响应。 */
    public static LoginResponse success(
            String accessToken,
            long expiresInSeconds,
            String userId,
            String displayName,
            Set<String> permissions,
            Instant issuedAt) {
        return new LoginResponse(
                "SUCCESS",
                null,
                null,
                null,
                null,
                accessToken,
                "Bearer",
                expiresInSeconds,
                userId,
                displayName,
                permissions,
                issuedAt);
    }
}
