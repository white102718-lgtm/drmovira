package com.adpulse.system.loginlog.model;

/** 登录日志中的认证阶段。 */
public enum LoginAuthStage {
    PASSWORD(1),
    MFA_BIND(2),
    MFA_VERIFY(3),
    FEISHU_QR(4);

    private final int code;

    LoginAuthStage(int code) {
        this.code = code;
    }

    /** 返回数据库和接口使用的稳定阶段编码。 */
    public int getCode() {
        return code;
    }
}
