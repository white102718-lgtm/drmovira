package com.adpulse.system.common.security;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.exception.BusinessException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

/** 提供当前登录身份的统一读取方式。 */
public final class SecurityContextHelper {

    private SecurityContextHelper() {}

    /** 获取当前登录用户。 */
    public static CurrentUser currentUser() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null
                || !(authentication.getPrincipal() instanceof CurrentUser user)) {
            throw new BusinessException(ApiCode.SESSION_INVALID, "当前会话未认证");
        }
        return user;
    }

    /** 获取当前用户ID。 */
    public static Long currentUserId() {
        return currentUser().userId();
    }
}
