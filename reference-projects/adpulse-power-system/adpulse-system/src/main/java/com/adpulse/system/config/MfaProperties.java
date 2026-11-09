package com.adpulse.system.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** MFA密钥保护、签发方和临时挑战配置。 */
@ConfigurationProperties(prefix = "adpulse.security.mfa")
public record MfaProperties(
        String encryptionKey, String issuer, Duration challengeTtl, int maxAttempts) {}
