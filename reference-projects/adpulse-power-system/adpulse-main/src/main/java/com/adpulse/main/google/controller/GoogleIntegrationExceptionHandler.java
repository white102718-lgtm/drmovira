package com.adpulse.main.google.controller;

import com.adpulse.main.google.client.GoogleProviderClient.GoogleProviderException;
import com.adpulse.main.google.service.GoogleIntegrationService.GoogleIntegrationException;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Google数据集成异常响应映射。 */
@RestControllerAdvice(assignableTypes = GoogleIntegrationController.class)
public class GoogleIntegrationExceptionHandler {
    /** 映射业务、OAuth state和第三方连接异常。 */
    @ExceptionHandler({
        GoogleIntegrationException.class,
        GoogleProviderException.class,
        IllegalArgumentException.class
    })
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
