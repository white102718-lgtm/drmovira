package com.adpulse.system.auth.model;

/** MFA绑定或验证阶段保存在Redis中的短期认证上下文。 */
public record MfaChallenge(
        Long userId, String clientIp, Purpose purpose, String pendingSecretCiphertext) {

    /** MFA挑战用途。 */
    public enum Purpose {
        BIND,
        VERIFY
    }
}
