package com.adpulse.system.common.api;

/**
 * API 三位业务响应码。
 *
 * <p>首位同时表达前端处理策略：2xx 为成功，4xx 为前端流程型静默错误，5xx 为应向用户展示的业务错误，6xx 为仅记录日志的系统错误。
 */
public final class ApiCode {

    public static final int SUCCESS = 200;

    public static final int AUTHENTICATION_FAILED = 400;
    public static final int SESSION_INVALID = 401;
    public static final int ACCESS_DENIED = 403;
    public static final int MFA_CHALLENGE_INVALID = 410;
    public static final int MFA_CHALLENGE_MISMATCH = 411;
    public static final int MFA_STATE_CHANGED = 412;
    public static final int MFA_CODE_INVALID = 413;
    public static final int MFA_ATTEMPTS_EXCEEDED = 414;

    public static final int BUSINESS_ERROR = 500;
    public static final int VALIDATION_ERROR = 501;
    public static final int DUPLICATE_DATA = 502;
    public static final int RESOURCE_NOT_FOUND = 503;
    public static final int BUSINESS_CONFLICT = 504;

    public static final int SYSTEM_ERROR = 600;

    private ApiCode() {}

    /** 校验业务响应码必须是三位整数。 */
    public static void requireThreeDigits(int code) {
        if (code < 100 || code > 999) {
            throw new IllegalArgumentException("API业务响应码必须是三位整数: " + code);
        }
    }
}
