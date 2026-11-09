package com.adpulse.main.feishu.controller;

import com.adpulse.main.feishu.client.FeishuProviderClient.FeishuProviderException;
import com.adpulse.main.feishu.service.FeishuService.FeishuException;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 飞书同步异常响应映射。 */
@RestControllerAdvice(assignableTypes = FeishuController.class)
public class FeishuExceptionHandler {
    /** 映射业务与第三方连接异常。 */
    @ExceptionHandler({FeishuException.class, FeishuProviderException.class})
    public ApiResponse<Void> business(RuntimeException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }

    /** 映射请求字段校验异常。 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ApiResponse<Void> validation(MethodArgumentNotValidException exception) {
        String message =
                exception.getBindingResult().getFieldErrors().stream()
                        .findFirst()
                        .map(error -> error.getField() + error.getDefaultMessage())
                        .orElse("请求参数不完整");
        return ApiResponse.failure(ApiCode.VALIDATION_ERROR, message);
    }
}
