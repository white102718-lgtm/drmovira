package com.adpulse.system.common.exception;

import com.adpulse.system.common.api.ApiCode;

/** 可安全返回给客户端的业务异常。 */
public class BusinessException extends RuntimeException {

    private final int code;

    public BusinessException(int code, String message) {
        super(message);
        ApiCode.requireThreeDigits(code);
        this.code = code;
    }

    public int getCode() {
        return code;
    }

    /** 创建资源不存在异常。 */
    public static BusinessException notFound(String resource) {
        return new BusinessException(ApiCode.RESOURCE_NOT_FOUND, resource + "不存在");
    }

    /** 创建参数或业务状态冲突异常。 */
    public static BusinessException conflict(String message) {
        return new BusinessException(ApiCode.BUSINESS_CONFLICT, message);
    }

    /** 创建应直接展示给用户的参数校验异常。 */
    public static BusinessException validation(String message) {
        return new BusinessException(ApiCode.VALIDATION_ERROR, message);
    }
}
