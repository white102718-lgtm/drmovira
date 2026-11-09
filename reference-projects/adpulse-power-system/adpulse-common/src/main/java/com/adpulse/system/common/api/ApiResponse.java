package com.adpulse.system.common.api;

/**
 * 统一 HTTP 响应结构。
 *
 * @param code 三位业务状态码，首位表示前端处理策略
 * @param message 提示信息
 * @param data 响应数据
 * @param <T> 数据类型
 */
public record ApiResponse<T>(int code, String message, T data) {

    public ApiResponse {
        ApiCode.requireThreeDigits(code);
    }

    /** 创建成功响应。 */
    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>(ApiCode.SUCCESS, "success", data);
    }

    /** 创建无数据成功响应。 */
    public static ApiResponse<Void> success() {
        return success(null);
    }

    /** 创建失败响应。 */
    public static ApiResponse<Void> failure(int code, String message) {
        return new ApiResponse<>(code, message, null);
    }
}
