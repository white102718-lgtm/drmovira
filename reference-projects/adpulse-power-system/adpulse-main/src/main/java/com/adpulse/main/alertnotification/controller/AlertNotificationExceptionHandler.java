package com.adpulse.main.alertnotification.controller;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 预警配置接口异常响应映射。 */
@RestControllerAdvice(assignableTypes = AlertNotificationController.class)
public class AlertNotificationExceptionHandler {
    @ExceptionHandler({IllegalArgumentException.class, DataIntegrityViolationException.class})
    public ApiResponse<Void> business(RuntimeException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }

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
