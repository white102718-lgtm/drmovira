package com.ruoyi.system.orbit.config;

/** 可安全对用户展示的配置错误，不包含原始请求、平台响应或凭据。 */
public final class ConfigurationException extends RuntimeException {
    private final int status;
    private final String code;

    public ConfigurationException(int status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public int status() {
        return status;
    }

    public String code() {
        return code;
    }
}
