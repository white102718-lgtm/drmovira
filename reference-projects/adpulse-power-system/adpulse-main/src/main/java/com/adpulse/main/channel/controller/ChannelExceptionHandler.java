package com.adpulse.main.channel.controller;

import com.adpulse.main.channel.service.ChannelService.ChannelException;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 渠道接口参数及业务错误转换。 */
@RestControllerAdvice(assignableTypes = ChannelController.class)
public class ChannelExceptionHandler {

    /** 返回可直接展示的渠道业务错误。 */
    @ExceptionHandler(ChannelException.class)
    public ApiResponse<Void> handleBusiness(ChannelException exception) {
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
        return ApiResponse.failure(ApiCode.DUPLICATE_DATA, "数据与现有有效记录重复");
    }
}
