package com.adpulse.system.common.security;

import java.util.Set;

/** 日报与绩效的全员查看权限，填写及修改权限不随之扩大。 */
public final class DeliveryReportAccess {
    private static final Set<String> READ_ALL =
            Set.of("ROLE_AM", "ROLE_OPERATOR_LEADER", "ROLE_ADMIN");

    private DeliveryReportAccess() {}

    /** 只识别服务端会话授予的明确角色，不使用昵称或前端标志。 */
    public static boolean canReadAll(CurrentUser user) {
        return user.authorities() != null
                && user.authorities().stream()
                        .anyMatch(authority -> READ_ALL.contains(authority.getAuthority()));
    }
}
