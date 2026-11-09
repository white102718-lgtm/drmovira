package com.adpulse.system.auth.security;

import java.util.Optional;

/** 校验共享会话对应用户在当前服务中的实时访问资格。 */
public interface SessionUserValidator {

    /** 校验用户状态及来源IP策略，并返回展示信息。 */
    Optional<ValidatedUser> validate(Long userId, String clientIp);

    /** 已通过实时访问校验的用户摘要。 */
    record ValidatedUser(String displayName) {}
}
