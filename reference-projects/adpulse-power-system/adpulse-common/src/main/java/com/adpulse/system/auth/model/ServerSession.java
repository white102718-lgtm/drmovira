package com.adpulse.system.auth.model;

import java.time.Instant;
import java.util.Set;

/** Redis 中保存的权威登录会话。 */
public record ServerSession(
        String sessionId,
        Long userId,
        String displayName,
        String englishNickname,
        String realName,
        Long departmentId,
        String departmentName,
        Set<Long> roleIds,
        Set<String> roleCodes,
        Set<String> roleNames,
        String loginIp,
        Set<String> permissions,
        Set<String> menuCodes,
        Instant createdAt) {

    /** 读取升级前的 Redis 会话时，将缺失的菜单编码列表兼容为空集合。 */
    public ServerSession {
        menuCodes = menuCodes == null ? Set.of() : menuCodes;
    }

    /** 兼容未携带菜单编码列表的旧调用方。 */
    public ServerSession(
            String sessionId,
            Long userId,
            String displayName,
            String englishNickname,
            String realName,
            Long departmentId,
            String departmentName,
            Set<Long> roleIds,
            Set<String> roleCodes,
            Set<String> roleNames,
            String loginIp,
            Set<String> permissions,
            Instant createdAt) {
        this(
                sessionId,
                userId,
                displayName,
                englishNickname,
                realName,
                departmentId,
                departmentName,
                roleIds,
                roleCodes,
                roleNames,
                loginIp,
                permissions,
                Set.of(),
                createdAt);
    }
}
