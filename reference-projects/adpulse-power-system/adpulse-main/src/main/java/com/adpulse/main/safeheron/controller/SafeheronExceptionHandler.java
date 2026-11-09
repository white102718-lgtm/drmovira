package com.adpulse.main.safeheron.controller;

import com.adpulse.main.safeheron.service.SafeheronService.SafeheronException;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Safeheron接口参数和业务错误转换。 */
@RestControllerAdvice(assignableTypes = SafeheronController.class)
public class SafeheronExceptionHandler {

    /** 返回可直接展示的Safeheron业务错误。 */
    @ExceptionHandler(SafeheronException.class)
    public ApiResponse<Void> handleBusiness(SafeheronException exception) {
        return ApiResponse.failure(ApiCode.BUSINESS_CONFLICT, exception.getMessage());
    }

    /** 返回请求字段校验错误。 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ApiResponse<Void> handleValidation(MethodArgumentNotValidException exception) {
        String message =
                exception.getBindingResult().getFieldErrors().stream()
                        .findFirst()
                        .map(error -> error.getField() + error.getDefaultMessage())
                        .orElse("请求参数不合法");
        return ApiResponse.failure(ApiCode.VALIDATION_ERROR, message);
    }

    /** 返回唯一键冲突错误。 */
    @ExceptionHandler(DuplicateKeyException.class)
    public ApiResponse<Void> handleDuplicate(DuplicateKeyException exception) {
        return ApiResponse.failure(ApiCode.DUPLICATE_DATA, "归集配置与现有有效记录重复");
    }
}
